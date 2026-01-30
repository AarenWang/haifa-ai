package com.haifa.sreagent.example.fdleak;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class FdLeakController {
  private static final int MAX_FDS = 2048;

  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicInteger openPerSec = new AtomicInteger(0);
  private final AtomicInteger max = new AtomicInteger(0);
  private final AtomicInteger opened = new AtomicInteger(0);
  private volatile File dir;

  private final Object lock = new Object();
  private final List<FileInputStream> streams = new ArrayList<>();
  private volatile Thread worker;

  public void start(int openPerSec, int max, String dir) {
    stop();
    this.openPerSec.set(clamp(openPerSec, 1, 500));
    this.max.set(clamp(max, 1, MAX_FDS));
    this.dir = new File(dir == null || dir.isEmpty() ? "/tmp" : dir);
    this.dir.mkdirs();
    this.opened.set(0);
    this.running.set(true);

    Thread th = new Thread(this::runLoop, "fd-leak");
    th.setDaemon(true);
    this.worker = th;
    th.start();
  }

  private void runLoop() {
    while (running.get()) {
      if (opened.get() >= max.get()) {
        sleep(200);
        continue;
      }

      int burst = Math.max(1, openPerSec.get() / 10);
      for (int i = 0; i < burst && running.get(); i++) {
        if (opened.get() >= max.get()) {
          break;
        }
        tryOpenOne();
      }
      sleep(100);
    }
  }

  private void tryOpenOne() {
    try {
      File f = new File(dir, "fdleak-" + ThreadLocalRandom.current().nextInt(1_000_000) + ".txt");
      if (!f.exists()) {
        try (FileOutputStream out = new FileOutputStream(f)) {
          out.write("hello\n".getBytes(StandardCharsets.UTF_8));
        }
      }
      FileInputStream in = new FileInputStream(f);
      synchronized (lock) {
        streams.add(in);
        opened.incrementAndGet();
      }
    } catch (Exception ignored) {
      sleep(50);
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
      for (FileInputStream s : streams) {
        try {
          s.close();
        } catch (Exception ignored) {
        }
      }
      streams.clear();
      opened.set(0);
    }
    openPerSec.set(0);
    max.set(0);
  }

  public boolean isRunning() {
    return running.get();
  }

  public int opened() {
    return opened.get();
  }

  public int max() {
    return max.get();
  }

  public int openPerSec() {
    return openPerSec.get();
  }

  public String dir() {
    File d = dir;
    return d == null ? "" : d.getAbsolutePath();
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
