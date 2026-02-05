# A SLM-Based Automated Method to Evaluate the Expected Output of Graphical User Interface for Web Applications
This repository provides the dataset for the research paper: "A SLM-Based Automated Method to Evaluate the Expected Output of Graphical User Interface for Web Applications." The dataset is specifically designed for the Eu2Json task, which involves transforming natural language UI test descriptions into structured, executable JSON formats. This data supports the training and evaluation of **Small Language Models (SLMs)** in automating the verification of Graphical User Interface (GUI) expected outputs for web applications.

## Directory Structure
The repository is organized as follows:

```text
data/
├── train.xlsx       # Full training dataset (50,000 samples)
├── train_en.xlsx    # English-only training subset (~25,000 samples)
├── train_vi.xlsx    # Vietnamese-only training subset (~25,000 samples)
└── test.xlsx        # Test set for final evaluation
```
### Description:
- **train.xlsx**: The primary training dataset containing 50,000 samples with a balanced 1:1 ratio between Vietnamese and English.
- **train_en.xlsx** and **train_vi.xlsx**: Training data separated by language (English and Vietnamese).
- **test.xlsx**: A dataset used to calculate final performance metrics including Key Score, Value Score, and Satisfaction Score.

## Dataset Specifications
- **Training Size**: 50,000 samples.
- **Attribute coverage**: Includes approximately 150 common CSS properties.
