package com.haifa.sreagent.example.iowait;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class IoBurnController {
  private final AtomicBoolean running = new AtomicBoolean(false);
  private final AtomicInteger threads = new AtomicInteger(0);
  private final AtomicInteger mbPerOp = new AtomicInteger(0);
  private final AtomicBoolean fsync = new AtomicBoolean(false);
  private volatile Path dir = Paths.get("/tmp");
  private volatile ExecutorService pool;

  public synchronized void start(int threadCount, int mbPerOp, boolean fsync, String dir) {
    stop();
    int t = Math.max(1, threadCount);
    int mb = Math.max(1, mbPerOp);
    this.threads.set(t);
    this.mbPerOp.set(mb);
    this.fsync.set(fsync);
    this.dir = Paths.get(dir == null || dir.isEmpty() ? "/tmp" : dir);
    this.running.set(true);

    ThreadFactory tf = r -> {
      Thread th = new Thread(r);
      th.setDaemon(true);
      th.setName("io-burner-" + th.getId());
      return th;
    };
    this.pool = Executors.newFixedThreadPool(t, tf);
    for (int i = 0; i < t; i++) {
      this.pool.submit(new IoBurnTask(this.running, this.dir, this.mbPerOp, this.fsync));
    }
  }

  public synchronized void stop() {
    running.set(false);
    ExecutorService p = pool;
    pool = null;
    if (p != null) {
      p.shutdownNow();
      try {
        p.awaitTermination(2, TimeUnit.SECONDS);
      } catch (InterruptedException ignored) {
        Thread.currentThread().interrupt();
      }
    }
    threads.set(0);
    mbPerOp.set(0);
    fsync.set(false);
  }

  public boolean isRunning() {
    return running.get();
  }

  public int threadCount() {
    return threads.get();
  }

  public int mbPerOp() {
    return mbPerOp.get();
  }

  public boolean fsync() {
    return fsync.get();
  }

  public Path dir() {
    return dir;
  }
}
