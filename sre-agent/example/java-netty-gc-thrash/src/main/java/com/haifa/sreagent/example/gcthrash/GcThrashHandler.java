package com.haifa.sreagent.example.gcthrash;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

import java.util.List;
import java.util.Map;

public final class GcThrashHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final GcThrashController controller;

  public GcThrashHandler(GcThrashController controller) {
    this.controller = controller;
  }

  @Override
  protected void channelRead0(ChannelHandlerContext ctx, FullHttpRequest req) {
    QueryStringDecoder q = new QueryStringDecoder(req.uri());
    String path = q.path();
    HttpMethod method = req.method();

    if ("/health".equals(path)) {
      RespUtil.sendText(ctx, req, HttpResponseStatus.OK, "OK\n");
      return;
    }

    if ("/pid".equals(path)) {
      long pid = ProcessHandle.current().pid();
      String json = "{\"pid\":" + pid + ",\"java\":\"" + escape(System.getProperty("java.version")) + "\"}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/status".equals(path)) {
      String json = "{\"gc_running\":" + controller.isRunning()
          + ",\"threads\":" + controller.threadCount()
          + ",\"allocMbPerSec\":" + controller.allocMbPerSec()
          + ",\"chunkKb\":" + controller.chunkKb()
          + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/gc/start".equals(path) && HttpMethod.POST.equals(method)) {
      int threads = intParam(q.parameters(), "threads", Math.max(1, Runtime.getRuntime().availableProcessors() / 2));
      int alloc = intParam(q.parameters(), "allocMbPerSec", 512);
      int chunkKb = intParam(q.parameters(), "chunkKb", 64);
      controller.start(threads, alloc, chunkKb);
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/gc/stop".equals(path) && HttpMethod.POST.equals(method)) {
      controller.stop();
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    RespUtil.sendJson(ctx, req, HttpResponseStatus.NOT_FOUND, "{\"error\":\"not_found\"}");
  }

  private static int intParam(Map<String, List<String>> params, String key, int def) {
    List<String> vs = params.get(key);
    if (vs == null || vs.isEmpty()) return def;
    try {
      return Integer.parseInt(vs.get(0));
    } catch (Exception e) {
      return def;
    }
  }

  private static String escape(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
