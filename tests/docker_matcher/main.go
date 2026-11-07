// Command docker-ignore-matcher reads a .dockerignore and slash-separated paths
// as JSON on stdin, returning JSON booleans for Docker-style ignored matches.
// It calls upstream Moby/patternmatcher directly; its only inputs are files
// supplied by this package's own deployment tests.
package main

import (
	"encoding/json"
	"fmt"
	"github.com/moby/patternmatcher"
	"github.com/moby/patternmatcher/ignorefile"
	"os"
)

type Input struct {
	IgnoreFile string   `json:"ignore_file"`
	Paths      []string `json:"paths"`
}
type Output struct {
	Excluded map[string]bool `json:"excluded"`
}

func main() {
	var input Input
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		panic(err)
	}
	file, err := os.Open(input.IgnoreFile)
	if err != nil {
		panic(err)
	}
	defer file.Close()
	patterns, err := ignorefile.ReadAll(file)
	if err != nil {
		panic(err)
	}
	matcher, err := patternmatcher.New(patterns)
	if err != nil {
		panic(err)
	}
	result := Output{Excluded: map[string]bool{}}
	for _, path := range input.Paths {
		ignored, err := matcher.MatchesOrParentMatches(path)
		if err != nil {
			panic(fmt.Sprintf("%s: %v", path, err))
		}
		result.Excluded[path] = ignored
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		panic(err)
	}
}
