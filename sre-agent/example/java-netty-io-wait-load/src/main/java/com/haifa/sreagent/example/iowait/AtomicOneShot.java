package com.haifa.sreagent.example.iowait;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;
import java.util.concurrent.ThreadLocalRandom;

final class AtomicOneShot {
  private AtomicOneShot() {}

  static void writeOnce(String dir, int mb, boolean fsync) {
    Path d = Paths.get(dir == null || dir.isEmpty() ? "/tmp" : dir);
    try {
      Files.createDirectories(d);
    } catch (IOException ignored) {
    }

    ByteBuffer buf = ByteBuffer.allocateDirect(1 << 20);
    byte[] fill = new byte[buf.capacity()];
    ThreadLocalRandom.current().nextBytes(fill);

    Path p = d.resolve("io-once-" + ProcessHandle.current().pid() + "-" + System.nanoTime() + ".dat");
    try (FileChannel ch = FileChannel.open(p, EnumSet.of(StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE))) {
      for (int i = 0; i < Math.max(1, mb); i++) {
        buf.clear();
        buf.put(fill);
        buf.flip();
        while (buf.hasRemaining()) {
          ch.write(buf);
        }
      }
      if (fsync) {
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
