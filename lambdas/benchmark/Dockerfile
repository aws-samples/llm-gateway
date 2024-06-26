# Use a lightweight base image; here we're using the alpine variant for its small size
FROM golang:1.20-alpine as builder

# Set the working directory inside the container
WORKDIR /app

# Install git for fetching the dependencies
RUN apk add --no-cache git

# Copy go mod and sum files
COPY go.mod ./
COPY go.sum ./

RUN go env -w GOPROXY=direct
# RUN go get github.com/valyala/fasthttp
# RUN go mod tidy

# Download all dependencies. Dependencies will be cached if the go.mod and go.sum files are not changed
RUN go mod download

# Copy the source code into the container
COPY main.go .

# Build the application; ensure to enable CGO as it might be disabled in Alpine by default
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o server .

# Use a minimal runtime image
FROM scratch

# Copy the binary from the builder stage
COPY --from=builder /app/server /server

# Expose the port the server listens on
EXPOSE 8080

# Command to run the executable
ENTRYPOINT ["/server"]