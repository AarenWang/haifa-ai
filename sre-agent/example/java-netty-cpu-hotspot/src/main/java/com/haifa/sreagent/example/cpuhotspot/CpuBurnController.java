package com.haifa.sreagent.example.cpuhotspot;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class CpuBurnController {
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicInteger intensity = new AtomicInteger(0);
  private final List<Thread> threads = new ArrayList<>();

  public synchronized void start(int threadCount, int intensityPercent) {
    stop();
    int t = Math.max(1, threadCount);
    int i = Math.max(1, Math.min(100, intensityPercent));
    intensity.set(i);
    running.set(true);
    for (int n = 0; n < t; n++) {
      Thread th = new Thread(new CpuBurnTask(running, intensity), "cpu-burner-" + (n + 1));
      th.setDaemon(true);
      threads.add(th);
      th.start();
    }
  }

  public synchronized void stop() {
    running.set(false);
    for (Thread t : threads) {
      try {
        t.join(200);
      } catch (InterruptedException ignored) {
        Thread.currentThread().interrupt();
      }
    }
    threads.clear();
    intensity.set(0);
  }

  public boolean isRunning() {
    return running.get();
  }

  public int intensity() {
    return intensity.get();
  }

  public int threadCount() {
    synchronized (this) {
      return threads.size();
    }
  }
}
