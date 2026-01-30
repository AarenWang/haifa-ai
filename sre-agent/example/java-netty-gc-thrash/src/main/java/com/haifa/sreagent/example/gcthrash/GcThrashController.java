package com.haifa.sreagent.example.gcthrash;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class GcThrashController {
  private static final int MAX_ALLOC_MB_PER_SEC = 4096;

  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicInteger threads = new AtomicInteger(0);
  private final AtomicInteger allocMbPerSec = new AtomicInteger(0);
  private final AtomicInteger chunkKb = new AtomicInteger(0);
  private final List<Thread> workers = new ArrayList<>();

  public synchronized void start(int threadCount, int allocMbPerSec, int chunkKb) {
    stop();
    int t = clamp(threadCount, 1, 64);
    int a = clamp(allocMbPerSec, 1, MAX_ALLOC_MB_PER_SEC);
    int c = clamp(chunkKb, 1, 1024);
    this.threads.set(t);
    this.allocMbPerSec.set(a);
    this.chunkKb.set(c);
    this.running.set(true);

    for (int i = 0; i < t; i++) {
      Thread th = new Thread(() -> runLoop(), "gc-thrash-" + (i + 1));
      th.setDaemon(true);
      workers.add(th);
      th.start();
    }
  }

  private void runLoop() {
    // A rough pacer: allocate N chunks per 100ms.
    while (running.get()) {
      int a = allocMbPerSec.get();
      int ckb = chunkKb.get();
      int bytes = ckb * 1024;
      int chunksPerSec = Math.max(1, (a * 1024 * 1024) / bytes);
      int chunksPerSlice = Math.max(1, chunksPerSec / 10);
      long sliceStart = System.nanoTime();
      for (int i = 0; i < chunksPerSlice; i++) {
        byte[] buf = new byte[bytes];
        ThreadLocalRandom.current().nextBytes(buf);
      }
      long elapsedNs = System.nanoTime() - sliceStart;
      long sleepNs = 100_000_000L - elapsedNs;
      if (sleepNs > 0) {
        try {
          Thread.sleep(sleepNs / 1_000_000L, (int) (sleepNs % 1_000_000L));
        } catch (InterruptedException ignored) {
          Thread.currentThread().interrupt();
        }
      }
    }
  }

  public synchronized void stop() {
    running.set(false);
    for (Thread t : workers) {
      try {
        t.join(200);
      } catch (InterruptedException ignored) {
        Thread.currentThread().interrupt();
      }
    }
    workers.clear();
    threads.set(0);
    allocMbPerSec.set(0);
    chunkKb.set(0);
  }

  public boolean isRunning() {
    return running.get();
  }

  public int threadCount() {
    return threads.get();
  }

  public int allocMbPerSec() {
    return allocMbPerSec.get();
  }

  public int chunkKb() {
    return chunkKb.get();
  }

  private static int clamp(int v, int min, int max) {
    return Math.max(min, Math.min(max, v));
  }
}
