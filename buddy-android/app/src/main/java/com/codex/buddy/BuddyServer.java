package com.codex.buddy;

import android.util.Base64;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class BuddyServer {
    private static final String DEFAULT_STATE_JSON = "{\"type\":\"status\",\"mood\":\"idle\",\"title\":\"Ready\",\"body\":\"\"}";
    private static final String VERSION_JSON = "{\"ok\":true,\"name\":\"buddy\",\"version\":\"0.1.0\",\"package\":\"com.codex.buddy\"}";
    public interface EventSink {
        void onEvent(String json);
    }

    private static final String WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    private final int port;
    private final EventSink sink;
    private final List<WebSocketClient> wsClients = Collections.synchronizedList(new ArrayList<WebSocketClient>());
    private volatile boolean running;
    private volatile String stateJson = DEFAULT_STATE_JSON;
    private final File mediaDir = new File("/data/data/com.codex.buddy/files/media");
    private ServerSocket serverSocket;
    private Thread acceptThread;

    public BuddyServer(int port, EventSink sink) {
        this.port = port;
        this.sink = sink;
    }

    public void start() {
        if (running) {
            return;
        }
        running = true;
        acceptThread = new Thread(new Runnable() {
            @Override
            public void run() {
                acceptLoop();
            }
        }, "buddy-http");
        acceptThread.start();
    }

    public void stop() {
        running = false;
        try {
            if (serverSocket != null) {
                serverSocket.close();
            }
        } catch (IOException ignored) {
        }
        synchronized (wsClients) {
            for (WebSocketClient client : new ArrayList<WebSocketClient>(wsClients)) {
                client.close();
            }
        }
    }

    public String getState() {
        return stateJson;
    }

    public void setState(String json) {
        if (json == null || json.trim().length() == 0) {
            stateJson = DEFAULT_STATE_JSON;
        } else {
            stateJson = json;
        }
    }

    public void broadcast(String json) {
        synchronized (wsClients) {
            for (WebSocketClient client : new ArrayList<WebSocketClient>(wsClients)) {
                client.send(json);
            }
        }
    }

    private void acceptLoop() {
        try {
            serverSocket = new ServerSocket(port, 16, InetAddress.getByName("0.0.0.0"));
            while (running) {
                final Socket socket = serverSocket.accept();
                Thread worker = new Thread(new Runnable() {
                    @Override
                    public void run() {
                        handleSocket(socket);
                    }
                }, "buddy-client");
                worker.start();
            }
        } catch (IOException ignored) {
        }
    }

    private void handleSocket(Socket socket) {
        try {
            socket.setSoTimeout(30000);
            BufferedInputStream in = new BufferedInputStream(socket.getInputStream());
            BufferedOutputStream out = new BufferedOutputStream(socket.getOutputStream());
            Request request = readRequest(in);
            if (request == null) {
                socket.close();
                return;
            }
            if ("websocket".equalsIgnoreCase(request.headers.get("upgrade"))) {
                handleWebSocket(socket, in, out, request);
                return;
            }
            handleHttp(socket, out, request);
        } catch (IOException ignored) {
            try {
                socket.close();
            } catch (IOException ignoredAgain) {
            }
        }
    }

    private void handleHttp(Socket socket, OutputStream out, Request request) throws IOException {
        String method = request.method.toUpperCase(Locale.US);
        String path = request.path;
        mediaDir.mkdirs();
        if ("OPTIONS".equals(method)) {
            writeResponse(out, 204, "No Content", "text/plain", "");
        } else if ("GET".equals(method) && ("/health".equals(path) || "/api/health".equals(path))) {
            writeResponse(out, 200, "OK", "application/json", "{\"ok\":true,\"name\":\"buddy\"}");
        } else if ("GET".equals(method) && ("/state".equals(path) || "/api/state".equals(path))) {
            writeResponse(out, 200, "OK", "application/json", stateJson);
        } else if ("GET".equals(method) && ("/version".equals(path) || "/api/version".equals(path))) {
            writeResponse(out, 200, "OK", "application/json", VERSION_JSON);
        } else if (("GET".equals(method) || "HEAD".equals(method)) && path.startsWith("/media/")) {
            writeMedia(out, request, path.substring("/media/".length()), "HEAD".equals(method));
        } else if ("POST".equals(method) && "/api/upload".equals(path)) {
            writeResponse(out, 200, "OK", "application/json", handleUpload(request));
        } else if ("POST".equals(method) && ("/api/event".equals(path) || "/event".equals(path))) {
            String body = new String(request.body, "UTF-8");
            acceptEvent(body);
            writeResponse(out, 200, "OK", "application/json", "{\"ok\":true}");
        } else if ("POST".equals(method) && "/api/clear".equals(path)) {
            acceptEvent("{\"type\":\"clear\"}");
            writeResponse(out, 200, "OK", "application/json", "{\"ok\":true}");
        } else {
            writeResponse(out, 200, "OK", "text/html",
                    "<!doctype html><meta name=viewport content='width=device-width'><title>Buddy</title>"
                            + "<body style='font-family:sans-serif;background:#101214;color:#f6f3ec'>"
                            + "<h1>Buddy</h1><p>POST JSON to <code>/api/event</code>.</p></body>");
        }
        socket.close();
    }

    private String handleUpload(Request request) throws IOException {
        String name = request.headers.get("x-buddy-name");
        if (name == null || name.length() == 0) {
            name = "upload.bin";
        }
        String safeName = safeName(name);
        String fileName = System.currentTimeMillis() + "-" + safeName;
        File outFile = new File(mediaDir, fileName);
        long written = 0;
        FileOutputStream fileOut = new FileOutputStream(outFile);
        try {
            byte[] buffer = new byte[8192];
            int remaining = request.contentLength;
            while (remaining > 0) {
                int read = request.bodyInput.read(buffer, 0, Math.min(buffer.length, remaining));
                if (read < 0) {
                    throw new IOException("unexpected eof");
                }
                fileOut.write(buffer, 0, read);
                remaining -= read;
                written += read;
            }
        } finally {
            fileOut.close();
        }
        try {
            JSONObject object = new JSONObject();
            object.put("ok", true);
            object.put("url", "/media/" + fileName);
            object.put("size", written);
            object.put("mime", mimeFor(fileName));
            return object.toString();
        } catch (JSONException e) {
            return "{\"ok\":true}";
        }
    }

    private String safeName(String name) {
        String clean = name.replace('\\', '/');
        int slash = clean.lastIndexOf('/');
        if (slash >= 0) {
            clean = clean.substring(slash + 1);
        }
        clean = clean.replaceAll("[^A-Za-z0-9._-]", "_");
        if (clean.length() == 0) {
            clean = "upload.bin";
        }
        return clean;
    }

    private void writeMedia(OutputStream out, Request request, String name, boolean headOnly) throws IOException {
        String safe = safeName(name);
        File file = new File(mediaDir, safe);
        if (!file.exists() || !file.isFile()) {
            writeResponse(out, 404, "Not Found", "text/plain", "not found");
            return;
        }
        long fileLength = file.length();
        long start = 0;
        long end = fileLength - 1;
        boolean partial = false;
        String range = request.headers.get("range");
        if (range != null && range.startsWith("bytes=") && fileLength > 0) {
            String value = range.substring("bytes=".length()).split(",", 2)[0].trim();
            int dash = value.indexOf('-');
            try {
                if (dash == 0) {
                    long suffix = Long.parseLong(value.substring(1));
                    start = Math.max(0, fileLength - suffix);
                } else if (dash > 0) {
                    start = Long.parseLong(value.substring(0, dash));
                    if (dash < value.length() - 1) {
                        end = Long.parseLong(value.substring(dash + 1));
                    }
                }
                end = Math.min(end, fileLength - 1);
                if (start >= 0 && start <= end) {
                    partial = true;
                } else {
                    writeRangeNotSatisfiable(out, fileLength);
                    return;
                }
            } catch (NumberFormatException e) {
                writeRangeNotSatisfiable(out, fileLength);
                return;
            }
        }
        long contentLength = fileLength == 0 ? 0 : (end - start + 1);
        String headers = "HTTP/1.1 " + (partial ? "206 Partial Content" : "200 OK") + "\r\n"
                + "Content-Type: " + mimeFor(safe) + "\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Accept-Ranges: bytes\r\n"
                + (partial ? "Content-Range: bytes " + start + "-" + end + "/" + fileLength + "\r\n" : "")
                + "Content-Length: " + contentLength + "\r\n"
                + "Connection: close\r\n\r\n";
        out.write(headers.getBytes("UTF-8"));
        if (headOnly || contentLength == 0) {
            out.flush();
            return;
        }
        FileInputStream input = new FileInputStream(file);
        try {
            long skipped = 0;
            while (skipped < start) {
                long next = input.skip(start - skipped);
                if (next <= 0) {
                    break;
                }
                skipped += next;
            }
            byte[] buffer = new byte[8192];
            long remaining = contentLength;
            int read;
            while (remaining > 0 && (read = input.read(buffer, 0, (int) Math.min(buffer.length, remaining))) >= 0) {
                out.write(buffer, 0, read);
                remaining -= read;
            }
        } finally {
            input.close();
        }
        out.flush();
    }

    private void writeRangeNotSatisfiable(OutputStream out, long fileLength) throws IOException {
        String headers = "HTTP/1.1 416 Range Not Satisfiable\r\n"
                + "Content-Range: bytes */" + fileLength + "\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Content-Length: 0\r\n"
                + "Connection: close\r\n\r\n";
        out.write(headers.getBytes("UTF-8"));
        out.flush();
    }

    private String mimeFor(String name) {
        String lower = name.toLowerCase(Locale.US);
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".gif")) return "image/gif";
        if (lower.endsWith(".webp")) return "image/webp";
        if (lower.endsWith(".mp4")) return "video/mp4";
        if (lower.endsWith(".mp3")) return "audio/mpeg";
        if (lower.endsWith(".wav")) return "audio/wav";
        if (lower.endsWith(".ogg")) return "audio/ogg";
        if (lower.endsWith(".html") || lower.endsWith(".htm")) return "text/html; charset=utf-8";
        return "application/octet-stream";
    }

    private void acceptEvent(String json) {
        try {
            JSONObject object = new JSONObject(json);
            updateStateJson(object);
            sink.onEvent(object.toString());
            broadcast(object.toString());
        } catch (JSONException e) {
            String fallback = jsonObject("message", "Buddy", json);
            stateJson = fallback;
            sink.onEvent(fallback);
            broadcast(fallback);
        }
    }

    private void updateStateJson(JSONObject object) throws JSONException {
        String type = object.optString("type", "message");
        if ("response".equals(type) || "stop_audio".equals(type)) {
            return;
        }
        if ("clear".equals(type)) {
            stateJson = DEFAULT_STATE_JSON;
            return;
        }
        if ("stream_start".equals(type)) {
            stateJson = snapshotStreamStart(object).toString();
            return;
        }
        if ("stream_chunk".equals(type)) {
            JSONObject snapshot = currentStreamSnapshot(object);
            String existing = snapshot.optString("text", "");
            snapshot.put("text", trimStreamText(existing + object.optString("text", object.optString("append", "")), snapshot.optInt("maxChars", 12000)));
            stateJson = snapshot.toString();
            return;
        }
        if ("stream_meta".equals(type) || "agent_status".equals(type)) {
            JSONObject snapshot = currentStreamSnapshot(object);
            if (object.has("status")) {
                snapshot.put("mood", object.optString("status", snapshot.optString("mood", "running")));
            }
            if (object.has("petId")) {
                snapshot.put("petId", object.optString("petId", snapshot.optString("petId", "")));
            }
            if (object.has("petSpritesheetUrl")) {
                snapshot.put("petSpritesheetUrl", object.optString("petSpritesheetUrl", snapshot.optString("petSpritesheetUrl", "")));
            }
            if (object.has("petUrl")) {
                snapshot.put("petUrl", object.optString("petUrl", snapshot.optString("petUrl", "")));
            }
            if (object.has("agentKind")) {
                snapshot.put("agentKind", object.optString("agentKind", snapshot.optString("agentKind", "")));
            }
            String leftText = object.optString("title", object.optString("body", ""));
            if (leftText.length() > 0) {
                snapshot.put("title", leftText);
                snapshot.put("body", leftText);
            }
            stateJson = snapshot.toString();
            return;
        }
        if ("stream_end".equals(type)) {
            JSONObject snapshot = currentStreamSnapshot(object);
            String finalStatus = object.optString("status", object.optInt("exitCode", 0) == 0 ? "done" : "failed");
            snapshot.put("mood", finalStatus);
            snapshot.put("status", finalStatus);
            snapshot.put("active", false);
            stateJson = snapshot.toString();
            return;
        }
        stateJson = object.toString();
    }

    private JSONObject currentStreamSnapshot(JSONObject fallbackSource) throws JSONException {
        try {
            JSONObject existing = new JSONObject(stateJson);
            if ("stream_start".equals(existing.optString("type", ""))) {
                return existing;
            }
        } catch (JSONException ignored) {
        }
        return snapshotStreamStart(fallbackSource);
    }

    private JSONObject snapshotStreamStart(JSONObject source) throws JSONException {
        JSONObject snapshot = new JSONObject();
        snapshot.put("type", "stream_start");
        snapshot.put("streamId", source.optString("streamId", source.optString("id", "stream")));
        snapshot.put("title", source.optString("title", source.optString("body", "Agent")));
        snapshot.put("body", source.optString("body", source.optString("title", "")));
        snapshot.put("mood", source.optString("mood", source.optString("status", "running")));
        snapshot.put("petId", source.optString("petId", ""));
        snapshot.put("petSpritesheetUrl", source.optString("petSpritesheetUrl", ""));
        snapshot.put("petUrl", source.optString("petUrl", ""));
        snapshot.put("agentKind", source.optString("agentKind", ""));
        snapshot.put("maxLines", source.optInt("maxLines", 160));
        snapshot.put("maxChars", source.optInt("maxChars", 12000));
        snapshot.put("text", source.optString("text", ""));
        snapshot.put("active", source.optBoolean("active", true));
        snapshot.put("status", source.optString("status", "live"));
        return snapshot;
    }

    private String trimStreamText(String text, int maxChars) {
        if (text == null) {
            return "";
        }
        if (text.length() <= maxChars) {
            return text;
        }
        return text.substring(text.length() - maxChars);
    }

    private String jsonObject(String type, String title, String body) {
        try {
            JSONObject object = new JSONObject();
            object.put("type", type);
            object.put("title", title);
            object.put("body", body);
            return object.toString();
        } catch (JSONException e) {
            return "{\"type\":\"message\",\"title\":\"Buddy\",\"body\":\"\"}";
        }
    }

    private void handleWebSocket(Socket socket, BufferedInputStream in, OutputStream out, Request request) throws IOException {
        String key = request.headers.get("sec-websocket-key");
        if (key == null) {
            socket.close();
            return;
        }
        String accept = webSocketAccept(key);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes("UTF-8"));
        out.flush();

        WebSocketClient client = new WebSocketClient(socket);
        wsClients.add(client);
        client.send("{\"type\":\"hello\",\"name\":\"buddy\"}");
        client.send(stateJson);
        try {
            while (running && !socket.isClosed()) {
                String message = readWebSocketText(in);
                if (message == null) {
                    break;
                }
                acceptEvent(message);
            }
        } finally {
            wsClients.remove(client);
            client.close();
        }
    }

    private String webSocketAccept(String key) throws IOException {
        try {
            MessageDigest sha1 = MessageDigest.getInstance("SHA-1");
            byte[] digest = sha1.digest((key.trim() + WS_MAGIC).getBytes("UTF-8"));
            return Base64.encodeToString(digest, Base64.NO_WRAP);
        } catch (Exception e) {
            throw new IOException(e);
        }
    }

    private String readWebSocketText(InputStream in) throws IOException {
        int b0 = in.read();
        if (b0 < 0) {
            return null;
        }
        int b1 = in.read();
        if (b1 < 0) {
            return null;
        }
        int opcode = b0 & 0x0f;
        boolean masked = (b1 & 0x80) != 0;
        long length = b1 & 0x7f;
        if (length == 126) {
            length = ((long) in.read() << 8) | in.read();
        } else if (length == 127) {
            length = 0;
            for (int i = 0; i < 8; i++) {
                length = (length << 8) | in.read();
            }
        }
        byte[] mask = new byte[4];
        if (masked) {
            readFully(in, mask);
        }
        byte[] payload = new byte[(int) length];
        readFully(in, payload);
        if (masked) {
            for (int i = 0; i < payload.length; i++) {
                payload[i] = (byte) (payload[i] ^ mask[i % 4]);
            }
        }
        if (opcode == 8) {
            return null;
        }
        if (opcode != 1) {
            return "";
        }
        return new String(payload, "UTF-8");
    }

    private void readFully(InputStream in, byte[] buffer) throws IOException {
        int offset = 0;
        while (offset < buffer.length) {
            int read = in.read(buffer, offset, buffer.length - offset);
            if (read < 0) {
                throw new IOException("unexpected eof");
            }
            offset += read;
        }
    }

    private Request readRequest(BufferedInputStream in) throws IOException {
        String line = readLine(in);
        if (line == null || line.length() == 0) {
            return null;
        }
        String[] parts = line.split(" ");
        if (parts.length < 2) {
            return null;
        }
        Request request = new Request();
        request.method = parts[0];
        request.path = parts[1].split("\\?", 2)[0];
        String header;
        while ((header = readLine(in)) != null && header.length() > 0) {
            int index = header.indexOf(':');
            if (index > 0) {
                request.headers.put(header.substring(0, index).trim().toLowerCase(Locale.US),
                        header.substring(index + 1).trim());
            }
        }
        int contentLength = 0;
        if (request.headers.containsKey("content-length")) {
            try {
                contentLength = Integer.parseInt(request.headers.get("content-length"));
            } catch (NumberFormatException ignored) {
            }
        }
        request.contentLength = contentLength;
        request.bodyInput = in;
        if (contentLength > 0 && !("POST".equalsIgnoreCase(request.method) && "/api/upload".equals(request.path))) {
            request.body = new byte[contentLength];
            readFully(in, request.body);
        } else {
            request.body = new byte[0];
        }
        return request;
    }

    private String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int previous = -1;
        int current;
        while ((current = in.read()) != -1) {
            if (previous == '\r' && current == '\n') {
                byte[] bytes = buffer.toByteArray();
                return new String(bytes, 0, Math.max(0, bytes.length - 1), "UTF-8");
            }
            buffer.write(current);
            previous = current;
        }
        return buffer.size() == 0 ? null : buffer.toString("UTF-8");
    }

    private void writeResponse(OutputStream out, int code, String text, String contentType, String body) throws IOException {
        byte[] data = body.getBytes("UTF-8");
        String headers = "HTTP/1.1 " + code + " " + text + "\r\n"
                + "Content-Type: " + contentType + "; charset=utf-8\r\n"
                + "Access-Control-Allow-Origin: *\r\n"
                + "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                + "Access-Control-Allow-Headers: content-type, x-buddy-name\r\n"
                + "Content-Length: " + data.length + "\r\n"
                + "Connection: close\r\n\r\n";
        out.write(headers.getBytes("UTF-8"));
        out.write(data);
        out.flush();
    }

    private static class Request {
        String method;
        String path;
        byte[] body;
        int contentLength;
        InputStream bodyInput;
        final Map<String, String> headers = new HashMap<String, String>();
    }

    private static class WebSocketClient {
        private final Socket socket;

        WebSocketClient(Socket socket) {
            this.socket = socket;
        }

        void send(String message) {
            try {
                byte[] payload = message.getBytes("UTF-8");
                ByteArrayOutputStream frame = new ByteArrayOutputStream();
                frame.write(0x81);
                if (payload.length < 126) {
                    frame.write(payload.length);
                } else if (payload.length <= 65535) {
                    frame.write(126);
                    frame.write((payload.length >> 8) & 0xff);
                    frame.write(payload.length & 0xff);
                } else {
                    frame.write(127);
                    for (int i = 7; i >= 0; i--) {
                        frame.write((payload.length >> (8 * i)) & 0xff);
                    }
                }
                frame.write(payload);
                OutputStream out = socket.getOutputStream();
                synchronized (out) {
                    out.write(frame.toByteArray());
                    out.flush();
                }
            } catch (IOException ignored) {
                close();
            }
        }

        void close() {
            try {
                socket.close();
            } catch (IOException ignored) {
            }
        }
    }
}
