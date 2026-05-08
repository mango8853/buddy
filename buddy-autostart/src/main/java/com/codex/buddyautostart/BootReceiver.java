package com.codex.buddyautostart;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.SystemClock;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "BuddyAutostart";
    private static final String ACTION_TEST = "com.codex.buddyautostart.TEST";
    private static final int REQUEST_CODE_EARLY = 1001;
    private static final int REQUEST_CODE_LATE = 1002;

    @Override
    public void onReceive(final Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : "";
        Log.i(TAG, "received action=" + action);
        if (ACTION_TEST.equals(action)) {
            launchBuddy(context);
            return;
        }
        if (Intent.ACTION_USER_UNLOCKED.equals(action)) {
            launchBuddy(context);
            scheduleLaunch(context, 8000L, REQUEST_CODE_EARLY);
            return;
        }
        scheduleLaunch(context, 8000L, REQUEST_CODE_EARLY);
        scheduleLaunch(context, 30000L, REQUEST_CODE_LATE);
    }

    private void launchBuddy(Context context) {
        Log.i(TAG, "launching Buddy");
        context.startActivity(buildLaunchIntent());
    }

    private void scheduleLaunch(Context context, long delayMs, int requestCode) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarmManager == null) {
            Log.w(TAG, "AlarmManager unavailable");
            return;
        }
        PendingIntent pendingIntent = PendingIntent.getActivity(
            context,
            requestCode,
            buildLaunchIntent(),
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        long triggerAtMillis = SystemClock.elapsedRealtime() + delayMs;
        Log.i(TAG, "scheduling Buddy launch in " + delayMs + "ms");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            alarmManager.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAtMillis, pendingIntent);
        } else {
            alarmManager.setExact(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAtMillis, pendingIntent);
        }
    }

    private Intent buildLaunchIntent() {
        Intent intent = new Intent();
        intent.setClassName("com.codex.buddy", "com.codex.buddy.MainActivity");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return intent;
    }
}
