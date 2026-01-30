package com.haifa.sreagent.example.mempressure;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class MemPressureController {
  private static final int MAX_TARGET_MB = 2048;

  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicInteger targetMb = new AtomicInteger(0);
  private final AtomicInteger chunkMb = new AtomicInteger(0);
  private final AtomicInteger intervalMs = new AtomicInteger(0);
  private final AtomicInteger retainedMb = new AtomicInteger(0);

  private final Object lock = new Object();
  private final List<byte[]> retained = new ArrayList<>();
  private volatile Thread worker;

  public void start(int targetMb, int chunkMb, int intervalMs) {
    int t = clamp(targetMb, 1, MAX_TARGET_MB);
    int c = clamp(chunkMb, 1, 64);
    int it = clamp(intervalMs, 1, 10_000);
    stop();

    this.targetMb.set(t);
    this.chunkMb.set(c);
    this.intervalMs.set(it);
    this.retainedMb.set(0);
    this.running.set(true);

    Thread th = new Thread(this::runLoop, "mem-retainer");
    th.setDaemon(true);
    this.worker = th;
    th.start();
  }

  private void runLoop() {
    while (running.get()) {
      int current = retainedMb.get();
      int target = targetMb.get();
      if (current >= target) {
        sleep(intervalMs.get());
        continue;
      }

      int bytes = chunkMb.get() * 1024 * 1024;
      byte[] b = new byte[bytes];
      ThreadLocalRandom.current().nextBytes(b);
      synchronized (lock) {
        retained.add(b);
        retainedMb.addAndGet(chunkMb.get());
      }
      sleep(intervalMs.get());
    }
  }

  public void stop() {
    running.set(false);
    Thread th = worker;
    worker = null;
    if (th != null) {
      try {
        th.join(300);
      } catch (InterruptedException ignored) {
        Thread.currentThread().interrupt();
      }
    }
    synchronized (lock) {
      retained.clear();
      retainedMb.set(0);
    }
    targetMb.set(0);
    chunkMb.set(0);
    intervalMs.set(0);
  }

  public boolean isRunning() {
    return running.get();
  }

  public int targetMb() {
    return targetMb.get();
  }

  public int chunkMb() {
    return chunkMb.get();
  }

  public int intervalMs() {
    return intervalMs.get();
  }

  public int retainedMb() {
    return retainedMb.get();
  }

  public int retainedChunks() {
    synchronized (lock) {
      return retained.size();
    }
  }

  private static void sleep(int ms) {
    try {
      Thread.sleep(ms);
    } catch (InterruptedException ignored) {
      Thread.currentThread().interrupt();
    }
  }

  private static int clamp(int v, int min, int max) {
    return Math.max(min, Math.min(max, v));
  }
}
