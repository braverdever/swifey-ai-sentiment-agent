package kafka

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/Shopify/sarama"
)

const (
	ContractAddressesTopic = "contract_addresses"
)

type KeyMessage struct {
	PublicKey  string    `json:"public_key"`
	PrivateKey string    `json:"private_key"`
	CreatedAt  time.Time `json:"created_at"`
}

type Producer struct {
	producer sarama.SyncProducer
}

func NewProducer() (*Producer, error) {
	brokers := strings.Split(os.Getenv("KAFKA_BROKERS"), ",")
	if len(brokers) == 0 {
		return nil, fmt.Errorf("no Kafka brokers configured")
	}

	config := sarama.NewConfig()
	config.Producer.RequiredAcks = sarama.WaitForAll
	config.Producer.Retry.Max = 5
	config.Producer.Return.Successes = true

	producer, err := sarama.NewSyncProducer(brokers, config)
	if err != nil {
		return nil, fmt.Errorf("failed to create producer: %v", err)
	}

	return &Producer{producer: producer}, nil
}

func (p *Producer) PublishKey(publicKey, privateKey string) error {
	msg := KeyMessage{
		PublicKey:  publicKey,
		PrivateKey: privateKey,
		CreatedAt:  time.Now(),
	}

	jsonData, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal key message: %v", err)
	}

	message := &sarama.ProducerMessage{
		Topic: ContractAddressesTopic,
		Value: sarama.StringEncoder(jsonData),
		Key:   sarama.StringEncoder(publicKey),
	}

	_, _, err = p.producer.SendMessage(message)
	if err != nil {
		return fmt.Errorf("failed to send message: %v", err)
	}

	return nil
}

func (p *Producer) Close() error {
	if err := p.producer.Close(); err != nil {
		return fmt.Errorf("failed to close producer: %v", err)
	}
	return nil
} 