FROM golang:1.22

WORKDIR /src
COPY . .
RUN go build -o /bin/inventory ./cmd/server

EXPOSE 8080
CMD ["/bin/inventory"]
