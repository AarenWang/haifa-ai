package com.haifa.sreagent.example.threadpool;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class StarvationController {
  private final AtomicBoolean blocking = new AtomicBoolean(false);
  private final AtomicInteger sleepMs = new AtomicInteger(0);

  public void startBlocking(int sleepMs) {
    blocking.set(true);
    this.sleepMs.set(Math.max(1, Math.min(600_000, sleepMs)));
  }

  public void stopBlocking() {
    blocking.set(false);
    sleepMs.set(0);
  }

  public boolean isBlocking() {
    return blocking.get();
  }

  public int sleepMs() {
    return sleepMs.get();
  }
}
