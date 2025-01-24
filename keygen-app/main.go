package main

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/mihirpenugonda/swifey-sentiment-agent/keygen-app/kafka"
	"github.com/mr-tron/base58"
	ed25519 "golang.org/x/crypto/ed25519"
)

var (
	count          int
	totalGenerated int
	mutex          sync.Mutex
	suffixes       []string
	supabaseUrl    string
	supabaseKey    string
	kafkaProducer  *kafka.Producer
)

type TokenContract struct {
	PublicKey  string    `json:"public_key"`
	PrivateKey string    `json:"private_key"`
	CreatedAt  time.Time `json:"created_at"`
}

func init() {
	// Load suffixes from env
	suffixesEnv := os.Getenv("VANITY_SUFFIXES")
	if suffixesEnv != "" {
		suffixes = strings.Split(suffixesEnv, ",")
	} else {
		suffixes = []string{"LoVE", "LovE", "lovE", "love", "loVE"}
	}

	// Initialize Supabase configuration
	supabaseUrl = os.Getenv("SUPABASE_URL")
	supabaseKey = os.Getenv("SUPABASE_KEY")
	if supabaseUrl == "" || supabaseKey == "" {
		log.Fatal("SUPABASE_URL and SUPABASE_KEY environment variables must be set")
	}

	// Initialize Kafka producer
	producer, err := kafka.NewProducer()
	if err != nil {
		log.Fatalf("Failed to create Kafka producer: %v", err)
	}
	kafkaProducer = producer
}

func storeInSupabase(contract TokenContract) error {
	url := fmt.Sprintf("%s/rest/v1/token_contracts", supabaseUrl)
	jsonData, err := json.Marshal(contract)
	if err != nil {
		return fmt.Errorf("failed to marshal contract: %v", err)
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}

	req.Header.Set("apikey", supabaseKey)
	req.Header.Set("Authorization", "Bearer "+supabaseKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Prefer", "return=minimal")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("failed to store contract: status code %d", resp.StatusCode)
	}

	return nil
}

func generateKeyPairs(wg *sync.WaitGroup, jobs <-chan struct{}) {
	defer wg.Done()
	for range jobs {
		// Generate a new keypair
		publicKey, privateKey, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			log.Printf("Error generating keypair: %v", err)
			continue
		}

		// Convert public key to base58
		pubKeyStr := base58.Encode(publicKey)

		mutex.Lock()
		totalGenerated++
		// Check for any of the valid suffixes
		for _, suffix := range suffixes {
			if strings.HasSuffix(pubKeyStr, suffix) {
				count++
				privKeyHex := hex.EncodeToString(privateKey.Seed())
				
				// Store in Supabase
				contract := TokenContract{
					PublicKey:  pubKeyStr,
					PrivateKey: privKeyHex,
					CreatedAt:  time.Now(),
				}
				if err := storeInSupabase(contract); err != nil {
					log.Printf("Error storing key in Supabase: %v", err)
				}

				// Publish to Kafka
				if err := kafkaProducer.PublishKey(pubKeyStr, privKeyHex); err != nil {
					log.Printf("Error publishing key to Kafka: %v", err)
				}
				break
			}
		}
		mutex.Unlock()
	}
}

func logProgress(stopChan <-chan struct{}) {
	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			mutex.Lock()
			log.Printf("Generated %d total addresses, %d matching addresses with suffixes %v", totalGenerated, count, suffixes)
			mutex.Unlock()
		case <-stopChan:
			return
		}
	}
}

func main() {
	log.Println("Starting Solana vanity address generator...")
	log.Printf("Looking for addresses with suffixes: %v", suffixes)

	defer kafkaProducer.Close()

	workers := runtime.NumCPU()
	jobs := make(chan struct{}, workers*2)
	var wg sync.WaitGroup
	stopChan := make(chan struct{})

	// Start logging progress
	go logProgress(stopChan)

	// Start workers
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go generateKeyPairs(&wg, jobs)
	}

	// Feed jobs efficiently
	go func() {
		for {
			jobs <- struct{}{}
		}
	}()

	wg.Wait()
	close(stopChan)
}