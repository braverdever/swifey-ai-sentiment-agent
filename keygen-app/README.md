# Key Generator Application

A Go application that generates ED25519 key pairs and publishes them to a Kafka topic.

## Features

- Generates ED25519 key pairs
- Saves key pairs to local files
- Publishes key pairs to a Kafka topic
- Configurable number of worker threads
- Supports Docker deployment

## Prerequisites

- Go 1.21 or later
- Docker and Docker Compose
- Apache Kafka

## Environment Variables

- `KAFKA_BROKERS`: Kafka broker addresses (default: "kafka:9092")
- `WORKER_THREADS`: Number of worker threads (default: number of CPU cores)
- `KEYS_DIR`: Directory to store generated keys (default: "keys")

## Building and Running

### Using Docker Compose

```bash
docker-compose up -d
```

### Manual Build

```bash
go mod download
go build -o keygen-app
./keygen-app
```

## Architecture

The application uses a multi-threaded approach to generate key pairs efficiently:

1. Multiple worker goroutines generate ED25519 key pairs
2. Each key pair is saved to a file in the specified directory
3. Key pairs are published to a Kafka topic for further processing

## Kafka Integration

The application publishes key pairs to the "generated-keys" topic with the following message format:

```json
{
  "public_key": "base58_encoded_public_key",
  "private_key": "hex_encoded_private_key",
  "timestamp": "2024-03-14T12:00:00Z"
}
```

## License

MIT License
