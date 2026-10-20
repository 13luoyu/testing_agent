import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftConfig, PeftModel


def try_llama2():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained('../model/pretrained/Atom-7B', device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True, attn_implementation="flash_attention_2")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained('../model/pretrained/Atom-7B',use_fast=False, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    input_ids = tokenizer(['<s>Human: 什么是叶绿素？\n</s><s>Assistant: '], return_tensors="pt", add_special_tokens=False).input_ids

    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda')

    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
        "do_sample":True,
        "top_k":50,
        "top_p":0.95,
        "temperature":0.3,
        "repetition_penalty":1.3,
        "eos_token_id":tokenizer.eos_token_id,
        "bos_token_id":tokenizer.bos_token_id,
        "pad_token_id":tokenizer.pad_token_id
    }
    # generate_input = {
    #     "input_ids": input_ids
    # }

    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)


def try_llama3():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/Meta-Llama-3-8B-Instruct", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True, attn_implementation="flash_attention_2")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/Meta-Llama-3-8B-Instruct", use_fast=False, trust_remote_code=True)

    # Role = Literal["system", "user", "assistant"]
    prompt = "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n你是一个生物学的专家。<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n请问什么是叶绿素？<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    input_ids = tokenizer([prompt], return_tensors="pt", add_special_tokens=False).input_ids
    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda')

    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
        "do_sample":True,
        "top_k":50,
        "top_p":0.95,
        "temperature":0.3,
        "repetition_penalty":1.3,
        "eos_token_id":tokenizer.eos_token_id,
        "bos_token_id":tokenizer.bos_token_id,
        "pad_token_id":tokenizer.pad_token_id
    }
    # generate_input = {
    #     "input_ids": input_ids
    # }

    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)



def try_internlm2():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/internlm2-7b", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True, attn_implementation="flash_attention_2")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/internlm2-7b", use_fast=False, trust_remote_code=True)

    input_ids = tokenizer(['<s><|im_start|>system\n你是一个生物学的专家<|im_end|>\n<|im_start|>user\n什么是叶绿素<|im_end|>\n<|im_start|>assistant\n'], return_tensors="pt", add_special_tokens=False).input_ids

    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda')

    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
        "do_sample":True,
        "top_k":50,
        "top_p":0.95,
        "temperature":0.3,
        "repetition_penalty":1.3,
        "eos_token_id":tokenizer.eos_token_id,
        "bos_token_id":tokenizer.bos_token_id,
        "pad_token_id":tokenizer.pad_token_id
    }
    # generate_input = {
    #     "input_ids": input_ids
    # }

    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)



def try_qwen2():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/Qwen2-7B-Instruct", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True, attn_implementation="flash_attention_2")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/Qwen2-7B-Instruct", use_fast=False, trust_remote_code=True)

    input_ids = tokenizer(['<|im_start|>system\n你是一个生物学的专家<|im_end|>\n<|im_start|>user\n什么是叶绿素<|im_end|>\n<|im_start|>assistant\n'], return_tensors="pt", add_special_tokens=False).input_ids

    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda')

    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
        "do_sample":True,
        "top_k":50,
        "top_p":0.95,
        "temperature":0.3,
        "repetition_penalty":1.3,
        "eos_token_id":tokenizer.eos_token_id,
        "bos_token_id":tokenizer.bos_token_id,
        "pad_token_id":tokenizer.pad_token_id
    }
    # generate_input = {
    #     "input_ids": input_ids
    # }

    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)


def try_glm4():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/glm-4-9b-chat", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/glm-4-9b-chat", use_fast=False, trust_remote_code=True)

    query = "什么是叶绿素"
    # input_ids = tokenizer.apply_chat_template([{"role": "user", "content": query}],
    #                                    add_generation_prompt=True,
    #                                    tokenize=True,
    #                                    return_tensors="pt",
    #                                    return_dict=True
    #                                    ).input_ids.to(device_map)
    # print(tokenizer.decode(inputs["input_ids"][0]))
    # exit(0)
    input_ids = tokenizer(['[gMASK]<sop><|system|>\n你是一个生物学的专家<|user|>\n什么是叶绿素<|assistant|>\n'], return_tensors="pt", add_special_tokens=False).input_ids
    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda')

    generate_input = {
        "input_ids":input_ids,
        # "max_new_tokens":512,
        # "do_sample":True,
        # "top_k":50,
        # "top_p":0.95,
        # "temperature":0.3,
        # "repetition_penalty":1.3,
        # "eos_token_id":tokenizer.eos_token_id,
        # "bos_token_id":tokenizer.bos_token_id,
        # "pad_token_id":tokenizer.pad_token_id
    }
    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)

def try_lora_glm4():
    model_name_or_path = "output/autonomous_driving/v3/glm4/best_lora_model_1733934410"

    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
    peft_config = PeftConfig.from_pretrained(model_name_or_path)
    model = AutoModelForCausalLM.from_pretrained(peft_config.base_model_name_or_path, device_map='cuda:0' if torch.cuda.is_available() else 'auto', torch_dtype=torch.bfloat16, trust_remote_code=True, quantization_config=bnb_config)
    model = PeftModel.from_pretrained(model, model_name_or_path, device_map="cuda:0" if torch.cuda.is_available() else "auto")
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(peft_config.base_model_name_or_path, use_fast=False, trust_remote_code=True)


    input_ids = tokenizer(['[gMASK]<sop><|system|>\n你是一个自动驾驶领域的专家。给出一条规则，请你抽取其中的规则元素并组合成R规则的形式。如果组合后的R规则存在冲突，则将其分成多条不冲突的R规则。<|user|>\n规则:在没有限速标志的路段，应当保持安全车速。<|assistant|>\n'], return_tensors="pt", add_special_tokens=False).input_ids
    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda:0')
    
    generate_input = {
        "input_ids":input_ids,
    }
    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)


def try_chatglm3():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/chatglm3-6b", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/chatglm3-6b", use_fast=False, trust_remote_code=True)

    input_ids = tokenizer(['[gMASK]sop<|user|>\n什么是叶绿素\n<|assistant|>\n'], return_tensors="pt", add_special_tokens=False).input_ids
    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda:0')
    
    # print(tokenizer.decode(input_ids[0]))
    # exit(0)
    
    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
    }
    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)


def try_qwen1_5():
    device_map = "cuda:0" if torch.cuda.is_available() else "auto"
    model = AutoModelForCausalLM.from_pretrained("../model/pretrained/Qwen1.5-4B-Chat", device_map=device_map, torch_dtype=torch.float16, trust_remote_code=True)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained("../model/pretrained/Qwen1.5-4B-Chat", use_fast=False, trust_remote_code=True)

    input_ids = tokenizer(['<|im_start|>user\n什么是叶绿素？<|im_end|>\n<|im_start|>assistant\n'], return_tensors="pt").input_ids
    if torch.cuda.is_available():
        input_ids = input_ids.to('cuda:0')
    
    # print(tokenizer.decode(input_ids[0]))
    # exit(0)
    
    generate_input = {
        "input_ids":input_ids,
        "max_new_tokens":512,
    }
    generate_ids  = model.generate(**generate_input)
    text = tokenizer.decode(generate_ids[0])
    print(text)




if __name__ == "__main__":
    # try_llama2()
    # try_llama3()
    # try_internlm2()
    # try_qwen2()
    # try_glm4()
    # try_lora_glm4()
    # try_chatglm3()
    try_qwen1_5()
