package com.codex.buddy;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.ToneGenerator;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "buddy";
    private static final String PREF_BRIDGE_URL = "bridge_url";
    private static final String PREF_LAST_STATE_JSON = "last_state_json";
    private WebView webView;
    private BuddyServer server;
    private PollBridgeClient pollBridgeClient;
    private MediaPlayer mediaPlayer;
    private ToneGenerator toneGenerator;
    private String currentAudioUrl = "";
    private boolean currentAudioLoop;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final List<String> pendingEvents = new ArrayList<String>();
    private volatile boolean webReady;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        enterImmersiveMode();

        webView = new WebView(this);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        webView.setVerticalScrollBarEnabled(false);
        webView.setHorizontalScrollBarEnabled(false);
        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new AppBridge(), "Buddy");
        setContentView(webView);
        webView.loadUrl("file:///android_asset/index.html");

        server = new BuddyServer(8787, new BuddyServer.EventSink() {
            @Override
            public void onEvent(final String json) {
                persistLastState(server.getState());
                dispatchToWebView(json);
            }
        });
        server.setState(loadLastState());
        server.start();
        configureBridge(getIntent());
    }

    @Override
    protected void onResume() {
        super.onResume();
        enterImmersiveMode();
    }

    @Override
    protected void onDestroy() {
        if (pollBridgeClient != null) {
            pollBridgeClient.stop();
        }
        if (server != null) {
            server.stop();
        }
        stopTonePlayer();
        stopAudioPlayer();
        super.onDestroy();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        configureBridge(intent);
    }

    private void enterImmersiveMode() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }

    private void dispatchToWebView(final String json) {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                if (!webReady) {
                    pendingEvents.add(json);
                    return;
                }
                String escaped = json.replace("\\", "\\\\").replace("'", "\\'");
                webView.evaluateJavascript("window.buddyApplyEvent(JSON.parse('" + escaped + "'))", null);
            }
        });
    }

    private void dispatchNow(String json) {
        String escaped = json.replace("\\", "\\\\").replace("'", "\\'");
        webView.evaluateJavascript("window.buddyApplyEvent(JSON.parse('" + escaped + "'))", null);
    }

    private void configureBridge(Intent intent) {
        String url = intent == null ? null : intent.getStringExtra("bridge_url");
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        if (url != null && url.trim().length() > 0) {
            prefs.edit().putString(PREF_BRIDGE_URL, url.trim()).apply();
        } else {
            url = prefs.getString(PREF_BRIDGE_URL, "");
        }
        if (url == null || url.trim().length() == 0) {
            return;
        }
        if (pollBridgeClient != null) {
            pollBridgeClient.stop();
        }
        pollBridgeClient = new PollBridgeClient(url.trim(), new PollBridgeClient.Listener() {
            @Override
            public void onEvent(String json) {
                dispatchToWebView(json);
            }
        });
        pollBridgeClient.start();
        dispatchToWebView("{\"type\":\"message\",\"mood\":\"linked\",\"title\":\"Bridge linked\",\"body\":\"" + escapeJson(url.trim()) + "\"}");
    }

    private String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private void persistLastState(String json) {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putString(PREF_LAST_STATE_JSON, json == null ? "" : json)
                .apply();
    }

    private String loadLastState() {
        return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .getString(PREF_LAST_STATE_JSON, "");
    }

    public class AppBridge {
        @JavascriptInterface
        public void send(String json) {
            if (server != null) {
                server.broadcast(json);
            }
            if (pollBridgeClient != null) {
                pollBridgeClient.postResponse(json);
            }
        }

        @JavascriptInterface
        public void ready() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    webReady = true;
                    if (pendingEvents.isEmpty() && server != null) {
                        dispatchNow(server.getState());
                        return;
                    }
                    for (String event : new ArrayList<String>(pendingEvents)) {
                        dispatchNow(event);
                    }
                    pendingEvents.clear();
                }
            });
        }

        @JavascriptInterface
        public void playAudio(final String url) {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    playAudioUrl(url, false);
                }
            });
        }

        @JavascriptInterface
        public void playAudioWithLoop(final String url, final boolean loop) {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    playAudioUrl(url, loop);
                }
            });
        }

        @JavascriptInterface
        public void stopAudio() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    stopAudioPlayer();
                }
            });
        }

        @JavascriptInterface
        public void pauseAudio() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    if (mediaPlayer != null && mediaPlayer.isPlaying()) {
                        mediaPlayer.pause();
                    }
                }
            });
        }

        @JavascriptInterface
        public void resumeAudio() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    if (mediaPlayer != null) {
                        mediaPlayer.start();
                    }
                }
            });
        }

        @JavascriptInterface
        public void restartAudio() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    if (mediaPlayer != null) {
                        mediaPlayer.seekTo(0);
                        if (!mediaPlayer.isPlaying()) {
                            mediaPlayer.start();
                        }
                    } else if (currentAudioUrl != null && currentAudioUrl.length() > 0) {
                        playAudioUrl(currentAudioUrl, currentAudioLoop);
                    }
                }
            });
        }

        @JavascriptInterface
        public String getAudioState() {
            if (mediaPlayer == null) {
                return "{\"playing\":false,\"position\":0,\"duration\":0,\"loop\":" + currentAudioLoop + "}";
            }
            int position = 0;
            int duration = 0;
            boolean playing = false;
            try {
                position = mediaPlayer.getCurrentPosition();
                duration = mediaPlayer.getDuration();
                playing = mediaPlayer.isPlaying();
            } catch (Exception ignored) {
            }
            return "{\"playing\":" + playing
                    + ",\"position\":" + position
                    + ",\"duration\":" + duration
                    + ",\"loop\":" + currentAudioLoop + "}";
        }

        @JavascriptInterface
        public void playDoneTone() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    playDoneChime();
                }
            });
        }

        @JavascriptInterface
        public void playWaitingTone() {
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    playWaitingChime();
                }
            });
        }
    }

    private void playAudioUrl(String url, boolean loop) {
        try {
            stopAudioPlayer();
            currentAudioUrl = url;
            currentAudioLoop = loop;
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setDataSource(url);
            mediaPlayer.setLooping(loop);
            mediaPlayer.setOnPreparedListener(new MediaPlayer.OnPreparedListener() {
                @Override
                public void onPrepared(MediaPlayer mp) {
                    mp.start();
                }
            });
            mediaPlayer.prepareAsync();
        } catch (Exception ignored) {
        }
    }

    private void stopAudioPlayer() {
        if (mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
        }
    }

    private ToneGenerator getToneGenerator() {
        if (toneGenerator == null) {
            toneGenerator = new ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90);
        }
        return toneGenerator;
    }

    private void playDoneChime() {
        try {
            final ToneGenerator tg = getToneGenerator();
            tg.startTone(ToneGenerator.TONE_PROP_ACK, 120);
            mainHandler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    try {
                        tg.startTone(ToneGenerator.TONE_PROP_BEEP2, 170);
                    } catch (Exception ignored) {
                    }
                }
            }, 140);
        } catch (Exception ignored) {
        }
    }

    private void playWaitingChime() {
        try {
            getToneGenerator().startTone(ToneGenerator.TONE_PROP_BEEP, 120);
        } catch (Exception ignored) {
        }
    }

    private void stopTonePlayer() {
        if (toneGenerator != null) {
            try {
                toneGenerator.release();
            } catch (Exception ignored) {
            }
            toneGenerator = null;
        }
    }
}
