package com.haifa.sreagent.example.deadlock;

import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.SimpleChannelInboundHandler;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.HttpMethod;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.QueryStringDecoder;

public final class DeadlockHandler extends SimpleChannelInboundHandler<FullHttpRequest> {
  private final DeadlockController controller;

  public DeadlockHandler(DeadlockController controller) {
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
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"deadlocks_created\":" + controller.created() + "}");
      return;
    }

    if ("/deadlock/start".equals(path) && HttpMethod.POST.equals(method)) {
      boolean ok = controller.tryCreateDeadlock();
      if (!ok) {
        RespUtil.sendJson(ctx, req, HttpResponseStatus.TOO_MANY_REQUESTS, "{\"ok\":false,\"error\":\"limit_reached\"}");
        return;
      }
      RespUtil.sendJson(ctx, req, HttpResponseStatus.OK, "{\"ok\":true}");
      return;
    }

    RespUtil.sendJson(ctx, req, HttpResponseStatus.NOT_FOUND, "{\"error\":\"not_found\"}");
  }

  private static String escape(String s) {
    if (s == null) return "";
    return s.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
