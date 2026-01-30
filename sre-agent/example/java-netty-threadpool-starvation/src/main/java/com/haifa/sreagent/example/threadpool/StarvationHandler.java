package com.haifa.sreagent.example.threadpool;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

import java.util.List;
import java.util.Map;

public final class StarvationHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final StarvationController controller;

  public StarvationHandler(StarvationController controller) {
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
      String json = "{\"blocking\":" + controller.isBlocking() + ",\"sleepMs\":" + controller.sleepMs() + "}";
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, json);
      return;
    }

    if ("/block/start".equals(path) && HttpMethod.POST.equals(method)) {
      int sleepMs = intParam(q.parameters(), "sleepMs", 3000);
      controller.startBlocking(sleepMs);
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/block/stop".equals(path) && HttpMethod.POST.equals(method)) {
      controller.stopBlocking();
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    if ("/work".equals(path) && HttpMethod.GET.equals(method)) {
      int ms = intParam(q.parameters(), "ms", 10);
      if (controller.isBlocking()) {
        sleep(controller.sleepMs());
      } else {
        sleep(Math.max(1, Math.min(60_000, ms)));
      }
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

  private static void sleep(int ms) {
    try {
      Thread.sleep(ms);
    } catch (InterruptedException ignored) {
      Thread.currentThread().interrupt();
    }
  }

  private static String escape(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
