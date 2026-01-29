package com.haifa.sreagent.example.cpuhotspot;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

final class CpuBurnTask implements Runnable {
  private static final long WORK_SLICE_NANOS = 5_000_000L; // 5ms

  private final AtomicBoolean running;
  private final AtomicInteger intensity;

  CpuBurnTask(AtomicBoolean running, AtomicInteger intensity) {
    this.running = running;
    this.intensity = intensity;
  }

  @Override
  public void run() {
    MessageDigest md = sha256();
    byte[] buf = new byte[256];
    ThreadLocalRandom.current().nextBytes(buf);

    while (running.get()) {
      int p = intensity.get();
      if (p <= 0) {
        LockSupport.parkNanos(1_000_000L);
        continue;
      }

      long start = System.nanoTime();
      while (running.get() && (System.nanoTime() - start) < WORK_SLICE_NANOS) {
        hotLoop(md, buf);
      }

      if (p < 100) {
        // sleep proportionally to reduce CPU usage
        long sleep = (long) (WORK_SLICE_NANOS * (100.0 - p) / p);
        LockSupport.parkNanos(Math.min(200_000_000L, sleep));
      }
    }
  }

  private static MessageDigest sha256() {
    try {
      return MessageDigest.getInstance("SHA-256");
    } catch (NoSuchAlgorithmException e) {
      throw new RuntimeException(e);
    }
  }

  // Intentionally named to be easy to spot in jstack.
  static void hotLoop(MessageDigest md, byte[] buf) {
    md.update(buf);
    byte[] out = md.digest();
    // small mixing to avoid JIT removing work
    for (int i = 0; i < buf.length; i++) {
      buf[i] ^= out[i % out.length];
    }
  }
}
