package com.haifa.sreagent.example.deadlock;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public final class DeadlockController {
  private static final int MAX_DEADLOCKS = 3;

  private final Object a = new Object();
  private final Object b = new Object();
  private final AtomicInteger created = new AtomicInteger(0);

  public int created() {
    return created.get();
  }

  public boolean tryCreateDeadlock() {
    if (created.get() >= MAX_DEADLOCKS) {
      return false;
    }
    created.incrementAndGet();

    CountDownLatch started = new CountDownLatch(2);
    Thread t1 = new Thread(() -> {
      started.countDown();
      synchronized (a) {
        sleep(50);
        synchronized (b) {
          // unreachable
        }
      }
    }, "deadlock-A-then-B-" + created.get());
    t1.setDaemon(true);

    Thread t2 = new Thread(() -> {
      started.countDown();
      synchronized (b) {
        sleep(50);
        synchronized (a) {
          // unreachable
        }
      }
    }, "deadlock-B-then-A-" + created.get());
    t2.setDaemon(true);

    t1.start();
    t2.start();
    try {
      started.await();
    } catch (InterruptedException ignored) {
      Thread.currentThread().interrupt();
    }
    return true;
  }

  private static void sleep(int ms) {
    try {
      Thread.sleep(ms);
    } catch (InterruptedException ignored) {
      Thread.currentThread().interrupt();
    }
  }
}
