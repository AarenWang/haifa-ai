package com.haifa.sreagent.example.mempressure;

import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.Channel;
import io.netty.channel.ChannelInitializer;
import io.netty.channel.ChannelOption;
import io.netty.channel.EventLoopGroup;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.HttpObjectAggregator;
import io.netty.handler.codec.http.HttpServerCodec;
import io.netty.handler.codec.http.HttpServerExpectContinueHandler;
import io.netty.handler.timeout.IdleStateHandler;
import io.netty.util.concurrent.DefaultEventExecutorGroup;
import io.netty.util.concurrent.DefaultThreadFactory;
import io.netty.util.concurrent.EventExecutorGroup;

import java.util.Locale;

public final class Main {
  public static void main(String[] args) throws Exception {
    int port = intArg(args, "--port", 8082);
    int bizThreads = intArg(args, "--biz-threads", Math.max(4, Runtime.getRuntime().availableProcessors()));

    MemPressureController controller = new MemPressureController();

    EventLoopGroup boss = new NioEventLoopGroup(1, new DefaultThreadFactory("boss", true));
    EventLoopGroup worker = new NioEventLoopGroup(0, new DefaultThreadFactory("worker", true));
    EventExecutorGroup biz = new DefaultEventExecutorGroup(bizThreads, new DefaultThreadFactory("biz", true));

    try {
      ServerBootstrap b = new ServerBootstrap();
      b.group(boss, worker)
          .channel(NioServerSocketChannel.class)
          .childOption(ChannelOption.TCP_NODELAY, true)
          .childOption(ChannelOption.SO_KEEPALIVE, true)
          .childHandler(new ChannelInitializer<SocketChannel>() {
            @Override
            protected void initChannel(SocketChannel ch) {
              ch.pipeline().addLast(new IdleStateHandler(0, 0, 120));
              ch.pipeline().addLast(new HttpServerCodec());
              ch.pipeline().addLast(new HttpObjectAggregator(1 << 20));
              ch.pipeline().addLast(new HttpServerExpectContinueHandler());
              ch.pipeline().addLast(biz, new MemPressureHandler(controller));
            }
          });

      Channel channel = b.bind(port).sync().channel();
      System.out.println("mem-pressure listening on 0.0.0.0:" + port + " bizThreads=" + bizThreads);

      Runtime.getRuntime().addShutdownHook(new Thread(() -> {
        controller.stop();
        try {
          channel.close().syncUninterruptibly();
        } catch (Exception ignored) {
        }
        boss.shutdownGracefully();
        worker.shutdownGracefully();
        biz.shutdownGracefully();
      }, "shutdown"));

      channel.closeFuture().sync();
    } finally {
      controller.stop();
      boss.shutdownGracefully();
      worker.shutdownGracefully();
      biz.shutdownGracefully();
    }
  }

  private static int intArg(String[] args, String key, int def) {
    for (int i = 0; i < args.length; i++) {
      if (key.equals(args[i]) && i + 1 < args.length) {
        return Integer.parseInt(args[i + 1]);
      }
      if (args[i].toLowerCase(Locale.ROOT).startsWith(key + "=")) {
        return Integer.parseInt(args[i].substring((key + "=").length()));
      }
    }
    return def;
  }
}
