#!/usr/bin/env python3
import os
import inspect
import logging
import numpy as np

from .utils import AttrDict, replace_text, print_table, ImageExtensions

ChatTemplates = {

    # https://huggingface.co/blog/llama2#how-to-prompt-llama-2
    'llama-2': {
        'system_prompt': "Answer the questions.",
        'system': '<s>[INST] <<SYS>>\n${MESSAGE}\n<</SYS>>\n\n',
        'first': '${MESSAGE} [/INST]',
        'user': '<s>[INST] ${MESSAGE} [/INST]',
        'bot': ' ${MESSAGE}'  # llama-2 output already ends in </s>
    },
    
    # https://github.com/lm-sys/FastChat/blob/main/docs/vicuna_weights_version.md#prompt-template
    'vicuna-v0': {
        'system_prompt': "A chat between a curious human and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the human's questions.",
        'system': '${MESSAGE}\n\n',
        'user': '### Human: ${MESSAGE}\n',
        'bot': '### Assistant: ${MESSAGE}\n',
    },
    
    'vicuna-v1': {
        'system_prompt': "A chat between a curious human and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the human's questions.",
        'system': '${MESSAGE}\n\n',
        'user': 'USER: ${MESSAGE}\n',
        'bot': 'ASSISTANT: ${MESSAGE}</s>\n', # TODO: does output already end in </s> ?
    },
}

ChatTemplates['llava-v0'] = ChatTemplates['vicuna-v0']
ChatTemplates['llava-v1'] = ChatTemplates['vicuna-v1']

ChatTemplates['llava-llama-2'] = ChatTemplates['llama-2'].copy()
ChatTemplates['llava-llama-2'].update({
    'system_prompt': "You are a helpful language and vision assistant. You are able to understand the visual content that the user provides, and assist the user with a variety of tasks using natural language."
})

for key in ChatTemplates:
    ChatTemplates[key] = AttrDict(ChatTemplates[key])
    

class ChatHistory():
    """
    Multimodal chat history that can contain a mix of media including text/images.
    
    ChatHistory objects can be indexed like a list of chat entry dicts,
    where each entry dict may have keys for 'text', 'image', 'role', ect.
    
       `chat_history[n]` will return the n-th chat entry

    Each type of media has a different embedding function (e.g. LLM's typically 
    do text token embedding internally, and images use CLIP + projection layers). 
    From these, it assembles the embedding for the entire chat as input to the LLM.
    
    It uses templating to add the required special tokens as defined by different
    model architectures.  In normal 2-turn chat, there are 'user' and 'bot' roles
    defined, but arbitrary roles can be added, each with their own template.
    The system prompt can also be configured through the chat template.
    
    TODO:  better caching of system prompt embeddings/ect
    """
    def __init__(self, model, template=None, system_prompt=None):
        """
        Parameters:
           
           model (LocalLM) -- the model instance used for embeddings
           
           template (str|dict) -- either a chat template dict, or the name of the 
                                  chat template to use like 'llama-2', 'vicuna-v1'
                                  If None, will attempt to determine model type.
                                  
           system_prompt (str) -- set the default system prompt
                                  if None, will use system prompt from the template.
        """
        self.model = model
        
        if not template:
            name = model.config.name.lower()
            if 'llama-2' in name:
                if 'llava' in name:
                    template = 'llava-llama-2'
                else:
                    template = 'llama-2'
            elif 'vicuna' in name:
                if 'v1' in name:
                    template = 'vicuna-v1'
                else:
                    template = 'vicuna-v0'
            elif 'llava' in name:
                if 'v1' in name:
                    template = 'llava-v1'
                else:
                    template = 'llava-v0'
            else:
                raise RuntimeError(f"Couldn't automatically determine model type from {model.config.name}, please set the --chat-template argument")
            
            logging.info(f"using chat template '{template}' for model {model.config.name}")
            
        if isinstance(template, str):
            self.template = ChatTemplates[template].copy()
        else:
            self.template = template
            
        if system_prompt:
            self.template['system_prompt'] = system_prompt

        self.embedding_functions = {}
        
        self.register_embedding('text', self.embed_text)
        self.register_embedding('dict', self.embed_dict)
        self.register_embedding('image', self.embed_image)
    
        self.reset()

    def __len__(self):
        """
        Returns the number of entries in the chat history
        """
        return len(self.entries)
        
    def __getitem__(self, entry):
        """
        Return the n-th chat entry with the subscript indexing operator
        """
        return self.entries[entry]
        
    def add_entry(self, role='user', input=None, **kwargs):
        """
        Add a chat entry consisting of text, image, ect.  Other inputs
        can be specified in kwargs that have registered embedding types.
        Role is the turn template to apply, typically 'user' or 'bot'.
        """
        self.entries.append(self.create_entry(role, input, **kwargs))
        return self.entries[-1]

    def create_entry(self, role='user', input=None, **kwargs):
        """
        Create a chat entry consisting of text, image, ect.  Other inputs
        can be specified in kwargs that have registered embedding types.
        Role is the turn template to apply, typically 'user' or 'bot'.
        """    
        entry = AttrDict(role=role, **kwargs)
        
        if input is not None:
            entry[self.embedding_type(input)] = input
            
        return entry

    def reset(self, add_system_prompt=True):
        """
        Reset the chat history, and optionally add the system prompt to the new chat.
        """
        self.entries = []
        self.kv_cache = None
        if add_system_prompt:
            self.add_entry(role='system', text=self.template['system_prompt'])
      
    @property
    def system_prompt(self):
        """
        Get the system prompt, the typically hidden instruction at the beginning
        of the chat like "You are a curious and helpful AI assistant, ..."
        """
        return self.template['system_prompt']
        
    @system_prompt.setter
    def system_prompt(self, instruction):
        """
        Set the system prompt instruction string and reset the chat history.
        TODO make it so this doesn't reset the chat history, but uncaches it.
        """
        self.template['system_prompt'] = instruction
        self.reset()
        
    def embed(self, input, type=None, template=None):
        """
        Get the embedding for a general input (text, image, ect)
        The embedding type will attempt to be determined automatically
        if it isn't explicitly specified. Paths that end in image extensions
        are assumed to be an image, otherwise strings are treated as text.
        """
        if not type:
            type = self.embedding_type(input)
            
        if type not in self.embedding_functions:
            raise ValueError(f"type '{type}' did not have an embedding registered")
            
        if self.embedding_functions[type].uses_template:
            return self.embedding_functions[type].func(input, template)
        else:
            return self.embedding_functions[type].func(input)
        
    def embed_text(self, text, template=None, use_cache=False):
        """
        Get the text embedding after applying the template for 'user', 'bot', ect.
        """
        if template:
            text = replace_text(template, {'${MESSAGE}': text})
        embedding = self.model.embed_text(text, use_cache=use_cache)
        logging.debug(f"embedding text {embedding.shape} {embedding.dtype} -> ```{text}```".replace('\n', '\\n'))
        return embedding
    
    def embed_dict(self, dict, template=None):
        """
        Get the embedding of a chat entry dict that can contain multiple embedding types.
        """
        embeddings = []
        
        for key, value in dict.items():
            if value is None:
                continue
            if key in self.embedding_functions:
                embeddings.append(self.embed(value, type=key, template=template))
                
        if len(embeddings) == 0:
            raise ValueError("dict did not contain any entries with valid embedding types")
        elif len(embeddings) == 1:
            return embeddings[0]
        else:
            return np.concatenate(embeddings, axis=1)
                
    def embed_image(self, image, template=None):
        """
        Given an image, extract features and perfom the image embedding.
        This uses the CLIP encoder and a projection model that
        maps it into the embedding space the model expects.
        
        This is only applicable to vision VLM's like Llava and Mini-GPT4,
        and will throw an exception if model.has_vision is False.
        """
        embeddings = [] 

        if template:
            template = template.split("${MESSAGE}")[0]
            embeddings.append(self.embed_text(template, use_cache=True))
            logging.debug(f"image template:  ```{template}```")
            
        embeddings.append(self.model.embed_image(image, return_tensors='np'))
        embeddings.append(self.embed_text('\n', use_cache=True))
        
        embeddings = np.concatenate(embeddings, axis=1)
        
        print_table(self.model.vision.stats)
        logging.debug(f"embedding image {embeddings.shape} {embeddings.dtype}")
        
        return embeddings

    def embed_chat(self, use_cache=True):
        """
        Assemble the embedding of either the latest or entire chat.
        If use_cache is true (the default), and only the new embeddings will be returned.
        If use_cache is set to false, then the entire chat history will be returned.
        Returns the embedding and its token position in the history.
        """
        embeddings = []
        position = 0
        
        num_user_prompts = 0
        open_user_prompt = False
        
        for i, entry in enumerate(self.entries):
            for key in entry.copy():
                if key not in self.embedding_functions or entry[key] is None:
                    continue

                if 'first' in self.template and entry['role'] == 'user' and num_user_prompts == 0:
                    role_template = self.template['first']  # if the first non-system message has a different template
                else:
                    if entry.role not in self.template:
                        raise RuntimeError(f"chat template {self.template_name} didn't have an entry for role={entry.role}")
                    role_template = self.template[entry.role]
                    if open_user_prompt:
                        role_template = role_template[role_template.find('${MESSAGE}'):] # user prompt needs closed out from an image
                        open_user_prompt = False
                
                embed_key = key + '_embedding'

                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"processing chat entry {i}  role='{entry.role}'  template='{role_template}'  open_user_prompt={open_user_prompt}  cached={'true' if embed_key in entry and use_cache else 'false'}  {key}='{entry[key]}'".replace('\n', '\\n'))
                
                if use_cache:
                    if embed_key not in entry: # TODO  and entry.role != 'bot'  -- only compute bot embeddings when needed
                        entry[embed_key] = self.embed(entry[key], type=key, template=role_template)
                        if entry.role != 'bot':  # bot outputs are already included in kv_cache
                            embeddings.append(entry[embed_key])
                            use_cache = False  # all entries after this need to be included
                            if key == 'image':
                                open_user_prompt = True  # image is inside first half of a user prompt
                        else:
                            position += entry[embed_key].shape[1]
                    else:
                        position += entry[embed_key].shape[1]
                else:
                    if embed_key not in entry:
                        entry[embed_key] = self.embed(entry[key], type=key, template=role_template)
                        if key == 'image':
                            open_user_prompt = True
                    embeddings.append(entry[embed_key])
                
                if entry['role'] == 'user' and key == 'text':
                    num_user_prompts += 1
                
        return np.concatenate(embeddings, axis=1), position

    def register_embedding(self, type, func):
        params = inspect.signature(func).parameters
        self.embedding_functions[type] = AttrDict(
            func=func,
            uses_template=len(params) > 1 #'role_template' in params
        )
        
    def embedding_type(self, input):
        if isinstance(input, str):
            if input.endswith(ImageExtensions):
                return 'image'
            else:
                return "text" 
        elif isinstance(input, PIL.Image.Image):
            return 'image'
        elif isinstance(input, list) and len(input) > 0 and isinstance(input[0], str):
            return 'text'
        else:
            raise ValueError(f"couldn't find type of embedding for {type(input)}, please specify the 'type' argument")
            