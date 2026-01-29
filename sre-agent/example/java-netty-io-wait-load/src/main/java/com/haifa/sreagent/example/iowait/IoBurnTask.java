package com.haifa.sreagent.example.iowait;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class IoBurnTask implements Runnable {
  private final AtomicBoolean running;
  private final Path dir;
  private final AtomicInteger mbPerOp;
  private final AtomicBoolean fsync;

  IoBurnTask(AtomicBoolean running, Path dir, AtomicInteger mbPerOp, AtomicBoolean fsync) {
    this.running = running;
    this.dir = dir;
    this.mbPerOp = mbPerOp;
    this.fsync = fsync;
  }

  @Override
  public void run() {
    ByteBuffer buf = ByteBuffer.allocateDirect(1 << 20); // 1MB
    byte[] fill = new byte[buf.capacity()];
    ThreadLocalRandom.current().nextBytes(fill);

    while (running.get()) {
      int mb = Math.max(1, mbPerOp.get());
      boolean doFsync = fsync.get();
      try {
        Files.createDirectories(dir);
      } catch (IOException ignored) {
      }

      Path p = dir.resolve("io-burn-" + ProcessHandle.current().pid() + "-" + Thread.currentThread().getId() + "-" + System.nanoTime() + ".dat");
      try (FileChannel ch = FileChannel.open(p, EnumSet.of(StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE))) {
        for (int i = 0; i < mb; i++) {
          buf.clear();
          buf.put(fill);
          buf.flip();
          while (buf.hasRemaining()) {
            ch.write(buf);
          }
        }
        if (doFsync) {
          ch.force(true);
        }
      } catch (IOException ignored) {
      } finally {
        try {
          Files.deleteIfExists(p);
        } catch (IOException ignored) {
        }
      }
    }
  }
}
