package com.haifa.sreagent.example.gcthrash;

import io.netty.buffer.Unpooled;
import io.netty.channel.ChannelFutureListener;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.http.DefaultFullHttpResponse;
import io.netty.handler.codec.http.FullHttpRequest;
import io.netty.handler.codec.http.FullHttpResponse;
import io.netty.handler.codec.http.HttpHeaderNames;
import io.netty.handler.codec.http.HttpHeaderValues;
import io.netty.handler.codec.http.HttpResponseStatus;
import io.netty.handler.codec.http.HttpVersion;

import java.nio.charset.StandardCharsets;

final class RespUtil {
  private RespUtil() {}

  static void sendJson(ChannelHandlerContext ctx, FullHttpRequest req, HttpResponseStatus st, String json) {
    byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
    FullHttpResponse resp = new DefaultFullHttpResponse(HttpVersion.HTTP_1_1, st, Unpooled.wrappedBuffer(bytes));
    resp.headers().set(HttpHeaderNames.CONTENT_TYPE, "application/json; charset=utf-8");
    resp.headers().setInt(HttpHeaderNames.CONTENT_LENGTH, bytes.length);
    boolean keepAlive = io.netty.handler.codec.http.HttpUtil.isKeepAlive(req);
    if (keepAlive) {
      resp.headers().set(HttpHeaderNames.CONNECTION, HttpHeaderValues.KEEP_ALIVE);
      ctx.writeAndFlush(resp);
    } else {
      ctx.writeAndFlush(resp).addListener(ChannelFutureListener.CLOSE);
    }
  }

  static void sendText(ChannelHandlerContext ctx, FullHttpRequest req, HttpResponseStatus st, String text) {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    FullHttpResponse resp = new DefaultFullHttpResponse(HttpVersion.HTTP_1_1, st, Unpooled.wrappedBuffer(bytes));
    resp.headers().set(HttpHeaderNames.CONTENT_TYPE, "text/plain; charset=utf-8");
    resp.headers().setInt(HttpHeaderNames.CONTENT_LENGTH, bytes.length);
    boolean keepAlive = io.netty.handler.codec.http.HttpUtil.isKeepAlive(req);
    if (keepAlive) {
      resp.headers().set(HttpHeaderNames.CONNECTION, HttpHeaderValues.KEEP_ALIVE);
      ctx.writeAndFlush(resp);
    } else {
      ctx.writeAndFlush(resp).addListener(ChannelFutureListener.CLOSE);
    }
  }
}
