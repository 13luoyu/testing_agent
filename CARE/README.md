# CARE

CARE is a prototype tool for automatically updating and reusing existing test cases when facing regulation changes. It is the official implementation for paper "[CARE: Cascading Impact-Aware Compliance Test Suite Evolution under Regulatory Changes](https://doi.org/10.1145/3832295)" accepted by **ISSTA 2026**. In response to frequent changes in regulatory rules, this paper proposes CARE, a cascading impact-aware framework for automated compliance testing evolution. Existing approaches often suffer from over-reuse or missed updates because they treat rule changes in isolation and ignore complex interdependencies across testing artifacts. CARE addresses this issue by constructing a unified four-layer cascading relation model spanning Rule-Requirement-Scenario-Test Case, enabling fine-grained traceability across abstraction levels. By explicitly modeling how rule changes propagate and amplify along this chain, the framework precisely identifies impacted scenarios and test cases that need updating, while safely maximizing the reuse of unaffected ones.

Experiments conducted on real-world compliance testing tasks across multiple domains show that CARE achieves an average F1 of 90.3\% on updated test suites, outperforming existing methods by up to 164\% and approaching expert-level effectiveness. Ablation studies further demonstrate that explicit cascading impact modeling and handling are key contributors to these improvements. In addition, CARE substantially reduces manual effort and improves test maintenance efficiency, and indicates strong cross-domain generalization. This work highlights cascading impact propagation as a central challenge in regulation-driven test maintenance and shows that shifting from isolated rule handling to cascading impact-aware evolution is essential for achieving both high test quality and maintenance efficiency. 

![Framework](./framework.png)




## 1 Evaluation Datasets and Prompts

### 1.1 Evaluation Datasets

The evaluation dataset is located in [data/evaluation_dataset/](./data/evaluation_dataset/) and contains benchmark data for experimental evaluation. The dataset is organized into four subdirectories:

| Directory | Description | Format |
|-----------|-------------|--------|
| [ini_rule/](./data/evaluation_dataset/ini_rule/) | Initial regulation documents before changes | PDF / TXT |
| [upd_rule/](./data/evaluation_dataset/upd_rule/) | Updated regulation documents after regulatory changes | PDF / TXT |
| [ini_testcase/](./data/evaluation_dataset/ini_testcase/) | Initial test case base corresponding to initial rules | JSON |
| [upd_testcase/](./data/evaluation_dataset/upd_testcase/) | Ground truth updated test cases after rule changes | JSON |

The dataset includes 11 datasets covering various financial regulatory domains such as Finance (Dataset 1-6), Automotive (Dataset 7-9), and Power (Dataset 10-11).

### 1.2 Prompts

The prompts are located in [data/prompt/](./data/prompt/) and are designed for LLM-based test case generation and evolution.

#### 1.2.1 Structured Requirement Generation

**File**: [structed_requirement_generation.txt](./data/prompt/structed_requirement_generation.txt)

This prompt is designed to transform natural language financial business rules into a structured format. Key features include:

- **Chain-of-Thought (CoT) Process**: Guides the LLM through element extraction, label assignment, requirement construction, and self-reflection
- **If-Then Rule Format**: Converts complex natural language rules into machine-interpretable `if condition then consequence` format
- **Predefined Label Set**: Provides a standardized tag system (Operator, Action, Target, Product, Method, Time, Quantity, Price, State, Event, etc.)
- **Flexible Tag Extension**: Supports domain-specific tag extension when predefined tags are insufficient
- **Multi-rule Decomposition**: Handles parallel conditions and nested logic by splitting into independent rules

#### 1.2.2 End-to-End Test Case Generation

**File**: [e2e_test_case_generation.txt](./data/prompt/e2e_test_case_generation.txt)

This prompt is designed for intelligently updating and reusing existing test case repositories when financial business requirements change. Key features include:

- **Change Identification**: Analyzes differences between original and new requirements to identify added, modified, or deleted rules
- **Cascading Impact Analysis**: Considers potential cascading impacts across related rules and test cases
- **Test Case Reuse**: Preserves test cases for unchanged rules to maximize asset reuse
- **Comprehensive Coverage**: Generates test cases covering positive scenarios, negative scenarios, and boundary conditions
- **Format Consistency**: Ensures output follows the input JSON structure for compatibility with existing test frameworks




## 2 Installation

### 2.1 Install step-by-step

All scripts are designed for and run on ***Ubuntu 22.04***.

1. Install dependencies.

    ```bash
    sudo apt update
    sudo apt upgrade -y
    sudo apt install build-essential zlib1g-dev libbz2-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev
    sudo apt-get install -y libgl1-mesa-dev
    sudo apt-get install libglib2.0-dev
    sudo apt install wget
    sudo apt install git
    ```

2. Install miniconda.

    ```bash
    cd ~
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh
    source ~/.bashrc
    ```

3. Create a virtual python environment and install all the required dependencies.
    ```bash
    git clone https://github.com/13luoyu/CARE.git
    cd CARE
    conda create -n CARE python=3.9
    conda activate CARE
    pip install -r requirements.txt

    # Install flash-attention based on your CUDA version. For example:
    wget https://github.com/Dao-AILab/flash-attention/releases/download/v2.5.6/flash_attn-2.5.6+cu118torch2.0cxx11abiFALSE-cp39-cp39-linux_x86_64.whl
    pip install flash_attn-2.5.6+cu118torch2.0cxx11abiFALSE-cp39-cp39-linux_x86_64.whl
    
    pip install -e .
    ```

4. Download / Config the used LLMs.
    We offer two ways to use LLM: calling a commercial LLM API or fine-tuning an LLM locally.

    **Option 1: Calling a commercial LLM API**
    To use a commercial LLM API, you need to obtain an API key from the provider. Then, put the API key in **api_key.json**.

    ```json
    {
        "baseURL": "...",
        "apiKey": "...",
        "model": "..."
    }
    ```

    **Option 2: Fine-tuning an LLM locally**
    To fine-tune an LLM locally, you need to download the pretrained model from HuggingFace.

    ```bash
    mkdir model
    mkdir model/pretrained
    mkdir model/trained
    git lfs install
    git clone https://huggingface.co/13luoyu/CARE
    cp -r CARE/* model/trained/
    rm -rf CARE

    cd model/pretrained
    git clone https://huggingface.co/THUDM/glm-4-9b-chat
    git clone https://huggingface.co/Qwen/Qwen3-8B
    cd ../..
    ```

5. Run a test demo.
    ```bash
    cd reuse
    python update_testcase.py
    ```
This step prefer API calls. If parameters like apikey are not filled in, the fine-tuned LLM will be used instead. After the command finishes running, the updated test cases are saved at **cache/new_testcase.json**.



## 3 Usage
We provide a streamlined interface, using commands to generate updated test cases for the updated document based on the initial document and initial test cases:

```bash
cd ours
python update_testcase.py --old_file {old_file} --old_testcases {old_testcases} --new_file {new_file} --new_testcases {new_testcases}
```

where {*old_file*} is the path of the initial regulation document, {*old_testcases*} is the path of the initial test case base, {*new_file*} is the path of the updated regulation document, and {*new_testcases*} is the file to save the output updated test cases.



## 4 Exeriment Evaluation

We provide the evaluation code generate the evaluation results in our paper. 

### Experiment I
To get the evaluation results for Experiment I in our paper, run the following command:

```bash
cd experiment/exp1
python generate_result_ours.py
# After the command finishes running, run
bash run_compute_acc.sh
bash run_compute_bsc.sh
bash run_compute_changed_rule_req_sce.sh
bash run_compute_reuse.sh
bash run_compute_testsuite_acc.sh
# Note that some commands may take a long time to run, and do not run them at the same time.
python draw_table.py
python draw_figure_2.py
python draw_figure_3.py
```

After running the above commands, you can get the result of Table 2 at **fig/exp1_table.csv**, Figure 7 (a) and (b) at **fig/exp1_var.pdf** and **fig/exp1_time.pdf**.

Table 2:
![Table 2](./experiment/exp1/fig/table2.png)

Figure 7 (a) and (b):
![Figure 7](./experiment/exp1/fig/exp1_var.png)
![Figure 7](./experiment/exp1/fig/exp1_time.png)



### Experiment II
```bash
To get the evaluation results for Experiment II in our paper, run the following command:
conda activate qwen
cd qwen3_service
nohup bash qwen3_service.sh >run.log &
sleep 30

cd ../experiment/exp2
conda activate testcase-reuse
python generate_testcase_no_requirement.py
python generate_testcase_no_scenario.py
python generate_testcase_directly.py
python generate_testcase_no_change_impact_analysis.py
python generate_testcase_ESIM.py
python generate_testcase_RPTSP.py
# After the command finishes running, run
bash run_compute_acc.sh
bash run_compute_bsc.sh
bash run_compute_changed_rule_req_sce.sh
bash run_compute_reuse.sh
bash run_compute_testsuite_acc.sh
# Note that some commands may take a long time to run, and do not run them at the same time.
python draw_table.py
```

After running the above commands, you can get the result of Table 4 at **fig/exp2_table.csv**.

Table 4:
![Table 4](./experiment/exp2/fig/table4.png)


### Experiment III
To get the evaluation results for Experiment III in our paper, run the following command:
```bash
cd experiment/exp2
python draw_figure.py
python draw_figure2.py
```

After running the above commands, you can get the result of Figure 8 (a) and (b) at **fig/exp2_step.pdf** and **fig/exp2_comp.pdf**.

Figure 8 (a) and (b):
![Figure 8](./experiment/exp2/fig/exp2_step.png)
![Figure 8](./experiment/exp2/fig/exp2_comp.png)


### Experiment IV
To get the evaluation results for Experiment IV in our paper, run the following command:
```bash
cd experiment/exp3
python generate_result_ours.py
# After the command finishes running, run
bash run_compute_acc.sh
bash run_compute_bsc.sh
bash run_compute_reuse.sh
bash run_compute_testsuite_acc.sh
# Note that some commands may take a long time to run, and do not run them at the same time.
python draw_table.py
```

After running the above commands, you can get the result of Figure 9 at **fig/exp3.pdf**.

Figure 9:
![Figure 9](./experiment/exp3/fig/exp3.png)




## 5 Project Structure

```
CARE/
├── data/                              # Data resources for evaluation and prompting
│   ├── evaluation_dataset/            # Benchmark datasets for experimental evaluation
│   │   ├── ini_rule/                  # Initial regulation documents (PDF/TXT format)
│   │   ├── upd_rule/                  # Updated regulation documents after changes
│   │   ├── ini_testcase/              # Initial test case base (JSON format)
│   │   └── upd_testcase/              # Ground truth updated test cases
│   └── prompt/                        # Prompt templates for LLM interactions
│       ├── structed_requirement_generation.txt   # Prompt for generating structured requirements
│       └── e2e_test_case_generation.txt          # Prompt for end-to-end test case generation
│
├── reuse/                             # Core module for test case reuse and evolution
│   ├── update_testcase.py             # Main entry point for updating test cases
│   ├── interface.py                   # Unified interface for running the framework
│   ├── process_nl_to_sci.py           # Process natural language to structured change info
│   ├── process_sci_to_sco.py          # Transform structured change info to change operations
│   ├── process_sco_to_fi.py           # Generate final impact analysis from change operations
│   ├── process_fi_to_fo.py            # Process final impact to final output
│   ├── process_fo_to_r.py             # Convert final output to rule representations
│   ├── process_r1_to_r2.py            # Stage 1 to Stage 2 rule transformation
│   ├── process_r2_to_r3.py            # Stage 2 to Stage 3 rule transformation
│   ├── process_r3_to_testcase.py      # Generate test cases from processed rules
│   ├── generate_test_case.py          # Test case generation utilities
│   ├── generate_linked_scenario.py    # Generate linked test scenarios
│   ├── rule_testcase_relation_mining.py  # Mine relationships between rules and test cases
│   ├── cache/                         # Runtime cache for intermediate results
│   └── domain_knowledge/              # Domain-specific knowledge base for financial regulations
│
├── experiment/                        # Experimental evaluation scripts and results
│   ├── exp1/                          # Experiment I: Main method comparison
│   ├── exp2/                          # Experiment II: Ablation study
│   ├── exp3/                          # Experiment III: Cross-domain generalization
│   ├── exp4/                          # Experiment IV: Different LLM comparison
│   └── exp5/                          # Motivation Experiment: Identification of Cascading Effect
│
├── support/                           # Supporting utilities and tools
│   ├── generate_scenario.py           # Scenario generation utilities
│   ├── generate_data_for_*.py         # Data preparation scripts for different LLMs
│   ├── compute_time.py                # Execution time computation
│   ├── compute_decoder_accuracy.py    # Decoder accuracy evaluation
│   ├── transfer_case_to_scenario.py   # Convert test cases to scenarios
│   ├── split_annotation_data.py       # Split annotated data for training/testing
│   ├── data_augment.py                # Data augmentation utilities
│   ├── llm4fin_scenario/              # LLM-generated financial scenarios
│   └── stopwords/                     # Chinese stopword lists for text processing
│
├── decoder_lora/                      # LoRA fine-tuning module for LLMs
│   ├── train.py                       # Main training entry point
│   ├── train_lora_model.py            # LoRA model training implementation
│   ├── predict.py                     # Model inference and prediction
│   ├── merge.py                       # Merge LoRA weights with base model
│   ├── model.py                       # Model architecture definitions
│   ├── dataset.py                     # Dataset loading and preprocessing
│   ├── arguments.py                   # Training argument configurations
│   ├── train_script/                  # Training shell scripts for different models
│   └── predict_data/                  # Prediction outputs for each fine-tuned model
│
├── transfer/                          # Format conversion utilities
│   ├── rules_to_mydsl.py              # Convert rules to domain-specific language (DSL)
│   ├── mydsl_to_rules.py              # Convert DSL back to rule format
│   └── knowledge_tree.py              # Knowledge tree construction for rule organization
│
├── qwen3_service/                     # Qwen3 model service for inference
│   ├── qwen3_service.py               # Service implementation
│   ├── qwen3_service.sh               # Service startup script
│   └── config.json                    # Service configuration
│
├── requirements.txt                   # Python package dependencies
├── setup.py                           # Package installation configuration
└── api_key.json                       # API key configuration for commercial LLMs
```





---

<div align="center">

*✨ Thanks for using **CARE**!*

</div>