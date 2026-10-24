package com.flowconsole.platform;

import java.net.http.*;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.Flow;

public final class BoundedHttp {
  private BoundedHttp() {}

  public static HttpResponse<byte[]> send(
      HttpClient client, HttpRequest request, int limit, int seconds) throws Exception {
    var future = client.sendAsync(request, info -> new LimitedBody(limit));
    try {
      return future.get(seconds, TimeUnit.SECONDS);
    } finally {
      if (!future.isDone()) future.cancel(true);
    }
  }

  private static class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
    final HttpResponse.BodySubscriber<byte[]> delegate = HttpResponse.BodySubscribers.ofByteArray();
    final int limit;
    long received;
    Flow.Subscription subscription;

    LimitedBody(int limit) {
      this.limit = limit;
    }

    @Override
    public CompletionStage<byte[]> getBody() {
      return delegate.getBody();
    }

    @Override
    public void onSubscribe(Flow.Subscription s) {
      subscription = s;
      delegate.onSubscribe(s);
    }

    @Override
    public void onNext(List<ByteBuffer> values) {
      for (var value : values) received += value.remaining();
      if (received > limit) {
        subscription.cancel();
        delegate.onError(new IllegalStateException("HTTP response exceeds limit"));
      } else delegate.onNext(values);
    }

    @Override
    public void onError(Throwable e) {
      delegate.onError(e);
    }

    @Override
    public void onComplete() {
      delegate.onComplete();
    }
  }
}
