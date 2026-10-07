# Upstream moved to source distribution; do not depend on removed image tags.
# Official release and build instructions: github.com/minio/minio/releases.
FROM golang:1.24.8 AS build
ENV CGO_ENABLED=0 GOMAXPROCS=2
# ponytail: two compiler jobs keep builds from starving an existing local demo.
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go install -p 2 github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM alpine:3.22
RUN apk add --no-cache ca-certificates curl && adduser -D -u 1000 minio \
    && mkdir /data && chown minio:minio /data
COPY --from=build /go/bin/minio /usr/local/bin/minio
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
