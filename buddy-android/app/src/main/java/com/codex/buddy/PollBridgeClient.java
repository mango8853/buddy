package com.codex.buddy;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

public class PollBridgeClient {
    public interface Listener {
        void onEvent(String json);
    }

    private final String baseUrl;
    private final Listener listener;
    private volatile boolean running;
    private Thread thread;

    public PollBridgeClient(String baseUrl, Listener listener) {
        this.baseUrl = trimSlash(baseUrl);
        this.listener = listener;
    }

    public void start() {
        if (running) {
            return;
        }
        running = true;
        thread = new Thread(new Runnable() {
            @Override
            public void run() {
                loop();
            }
        }, "buddy-poll");
        thread.start();
    }

    public void stop() {
        running = false;
        if (thread != null) {
            thread.interrupt();
        }
    }

    public void postResponse(final String json) {
        Thread worker = new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    post("/response", json);
                } catch (Exception ignored) {
                }
            }
        }, "buddy-response");
        worker.start();
    }

    private void loop() {
        while (running) {
            try {
                String body = get("/next?device=" + URLEncoder.encode("buddy", "UTF-8"));
                JSONObject payload = new JSONObject(body);
                JSONArray events = payload.optJSONArray("events");
                if (events != null) {
                    for (int i = 0; i < events.length(); i++) {
                        listener.onEvent(events.getJSONObject(i).toString());
                    }
                }
                Thread.sleep(1000);
            } catch (Exception ignored) {
                try {
                    Thread.sleep(2500);
                } catch (InterruptedException interrupted) {
                    return;
                }
            }
        }
    }

    private String get(String path) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(10000);
        connection.setRequestMethod("GET");
        return read(connection.getInputStream());
    }

    private void post(String path, String json) throws Exception {
        byte[] data = json.getBytes("UTF-8");
        HttpURLConnection connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(5000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("content-type", "application/json; charset=utf-8");
        connection.setFixedLengthStreamingMode(data.length);
        OutputStream out = connection.getOutputStream();
        out.write(data);
        out.close();
        read(connection.getInputStream());
    }

    private String read(InputStream input) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        int n;
        while ((n = input.read(chunk)) >= 0) {
            buffer.write(chunk, 0, n);
        }
        return buffer.toString("UTF-8");
    }

    private static String trimSlash(String value) {
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }
}
