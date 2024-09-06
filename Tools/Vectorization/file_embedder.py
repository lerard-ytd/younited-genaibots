import os
import re
import numpy as np
import pandas as pd
import logging
from bs4 import BeautifulSoup
from openai import AzureOpenAI, OpenAIError
import tiktoken
import urllib.parse
import json
import argparse
import colorama
from colorama import Fore, Style
import urllib.parse

help_description = """
File Embedder Script with Dynamic Chunking

This script processes documents (files or directories) to create embeddings using Azure OpenAI.
It handles segmentation of documents dynamically by either a fixed token count or based on document structure (paragraphs/headings).
It also provides the option to overlap chunks for better contextual continuity.

Usage:
  python file_embedder.py --input <input_path> --output <output_path> --output_format <csv|json>
                          --openai_key <api_key> --openai_endpoint <endpoint_url>
                          [--max_tokens <number>] [--index_name <name>]
                          [--openai_api_version <version>] [--dynamic_chunking] [--overlap_tokens <number>]
                          [--source_type <filesystem|azure_devops_wiki>] [--wiki_url <url>]

Arguments:
  --input              : Path to input file or directory (required).
                         This can be a single document or a directory containing multiple documents.
  --output             : Path to the output file without extension (required).
                         The script will generate either a CSV or JSON file based on the format you choose.
  --output_format      : Output format, either 'csv' or 'json' (default: csv).
                         Specifies the format for the embedding results. If not provided, the default is CSV.
  --openai_key         : Azure OpenAI API key (required).
                         Your API key to authenticate with Azure OpenAI services.
  --openai_endpoint    : Azure OpenAI endpoint URL (required).
                         The endpoint URL provided by Azure for your OpenAI instance.
  --max_tokens         : Maximum number of tokens per segment (optional).
                         If not provided, the entire document is processed in a single pass. Use this to limit the number of tokens in each chunk.
  --index_name         : Name for the Azure Cognitive Search index (optional).
                         If provided, an index definition will be generated based on the document embeddings.
  --openai_api_version : Azure OpenAI API version (optional, default: 2023-06-01-preview).
                         The API version to be used for the OpenAI services.
  --dynamic_chunking   : Enable chunking based on document structure such as paragraphs or headings (optional, default: False).
                         Allows dynamic chunking based on the structure of the document instead of a fixed token limit.
  --overlap_tokens     : Number of tokens to overlap between chunks (optional, default: 50).
                         This helps maintain continuity between chunks by repeating a certain number of tokens from the previous chunk.
  --model_name         : OpenAI model name to be used for generating embeddings (optional, default: 'text-embedding-3-large').
                         Specifies the OpenAI model to use for generating embeddings. You can provide a custom model if needed.
  --source_type        : Specify the source type for the file path (optional, default: 'filesystem').
                         'filesystem' (default): The file path is stored as the full local path.
                         'azure_devops_wiki': Converts the file path to an Azure DevOps Wiki URL.
  --wiki_url           : The base URL of your Azure DevOps Wiki.
                         This is required if you select 'azure_devops_wiki' as the source type.
                         Example: https://your-domain.visualstudio.com/your-project/_wiki/wikis/your-project.wiki

Examples:
1. Basic usage - Process a single file and output as CSV:
   python file_embedder.py --input /path/to/document.txt --output /path/to/output --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

2. Process a directory and output as JSON:
   python file_embedder.py --input /path/to/docs --output /path/to/output --output_format json --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

3. Process a file with a custom token limit and specific API version:
   python file_embedder.py --input /path/to/document.txt --output /path/to/output --max_tokens 500 --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT --openai_api_version 2023-05-15

4. Use dynamic chunking based on document structure with overlap tokens:
   python file_embedder.py --input /path/to/docs --output /path/to/output --output_format json --dynamic_chunking --overlap_tokens 100 --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

5. Process a directory and generate an Azure Cognitive Search index definition:
   python file_embedder.py --input /path/to/docs --output /path/to/output --index_name my_search_index --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

6. Use a custom model for embedding generation:
   python file_embedder.py --input /path/to/document.txt --output /path/to/output --model_name "your-custom-model" --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

7. Process a directory from an Azure DevOps Wiki:
   python file_embedder.py --input /path/to/docs --output /path/to/output --source_type azure_devops_wiki --wiki_url https://your-domain.visualstudio.com/your-project/_wiki/wikis/your-project.wiki --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT

8. Process with a mix of all options - token limit, dynamic chunking, overlap, and custom model:
   python file_embedder.py --input /path/to/docs --output /path/to/output --max_tokens 800 --dynamic_chunking --overlap_tokens 75 --model_name "your-custom-model" --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT --index_name my_search_index

9. Process a directory, limit tokens, use custom model and specific API version, output to JSON:
   python file_embedder.py --input /path/to/docs --output /path/to/output --output_format json --max_tokens 300 --model_name "text-embedding-2" --openai_api_version 2023-01-15 --openai_key YOUR_API_KEY --openai_endpoint YOUR_ENDPOINT
"""

colorama.init(autoreset=True)

# Configure logging with custom formatter for colored output
class ColoredFormatter(logging.Formatter):
    format_str = '%(asctime)s - %(levelname)s - %(message)s'

    FORMATS = {
        logging.DEBUG: Style.DIM + format_str + Style.RESET_ALL,
        logging.INFO: format_str,
        logging.WARNING: Fore.YELLOW + format_str + Style.RESET_ALL,
        logging.ERROR: Fore.RED + format_str + Style.RESET_ALL,
        logging.CRITICAL: Fore.RED + Style.BRIGHT + format_str + Style.RESET_ALL
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler (no color)
file_handler = logging.FileHandler('embedding_process.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Stream handler (with color)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(ColoredFormatter())
logger.addHandler(stream_handler)

# Parse command-line arguments
parser = argparse.ArgumentParser(description=help_description, formatter_class=argparse.RawTextHelpFormatter)

parser.add_argument('--input', required=True, help='Path to input file or directory')
parser.add_argument('--output', required=True, help='Path to output file (without extension)')
parser.add_argument('--output_format', choices=['csv', 'json'], default='csv', help='Output format (csv or json)')
parser.add_argument('--max_tokens', type=int, default=None, help='Maximum number of tokens per segment. If not set, entire documents will be vectorized.')
parser.add_argument('--index_name', help='Name for the Azure Cognitive Search index. If provided, an index definition will be generated.')
parser.add_argument('--openai_key', required=True, help='Azure OpenAI API key')
parser.add_argument('--openai_endpoint', required=True, help='Azure OpenAI endpoint')
parser.add_argument('--openai_api_version', default="2023-06-01-preview", help='Azure OpenAI API version')
parser.add_argument('--dynamic_chunking', action='store_true', help='Enable chunking based on document structure such as paragraphs or headings')
parser.add_argument('--overlap_tokens', type=int, default=50, help='Number of tokens to overlap between chunks')
parser.add_argument('--model_name', default="text-embedding-3-large", help="OpenAI model name to be used for generating embeddings. Default is 'text-embedding-3-large'")
parser.add_argument('--source_type', choices=['filesystem', 'azure_devops_wiki'], default='filesystem', 
                    help="Source type: 'filesystem' (default) or 'azure_devops_wiki'. Specifies how the file path is treated.")
parser.add_argument('--wiki_url', help="Base URL of the Azure DevOps Wiki. Required if 'azure_devops_wiki' is selected as source_type.")
args = parser.parse_args()

if args.source_type == 'azure_devops_wiki':
    if not args.wiki_url:
        raise ValueError("You must provide --wiki_url when using 'azure_devops_wiki' as source_type")

def get_file_path(local_path, source_type, wiki_url, input_dir):
    if source_type == 'filesystem':
        return local_path
    elif source_type == 'azure_devops_wiki':
        return create_wiki_url(wiki_url, local_path, input_dir)
    else:
        raise ValueError(f"Invalid source_type: {source_type}")
    
def create_wiki_url(wiki_base_url, local_file_path, input_dir):
    # Get the relative path from the input directory
    relative_path = os.path.relpath(local_file_path, input_dir)
    
    # Replace backslashes with forward slashes (for Windows paths)
    relative_path = relative_path.replace('\\', '/')

    # Remove .md extension if present
    if relative_path.lower().endswith('.md'):
        relative_path = os.path.splitext(relative_path)[0]
    
    # Encode the relative path
    encoded_path = urllib.parse.quote(relative_path)
    
    # Construct and return the full wiki URL with pagePath parameter
    return f"{wiki_base_url}?pagePath=/{encoded_path}"

file_paths = []

# Main processing logic to determine file paths and process files
if os.path.isdir(args.input):
    for root, dirs, files in os.walk(args.input):
        for file in files:
            local_file_path = os.path.join(root, file)
            file_path = get_file_path(local_file_path, args.source_type, args.wiki_url, args.input)
            
            logging.info(f"Processing file at: {file_path}")
            
            try:
                with open(local_file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except Exception as e:
                logging.error(f"Failed to read file {local_file_path}: {e}")
                continue
            # Ensure the correct file_path (DevOps Wiki URL or local path) is stored
            file_paths.append(file_path)  # Append the correct URL            

else:
    local_file_path = args.input
    file_path = get_file_path(local_file_path, args.source_type, args.wiki_url, os.path.dirname(args.input))
    
    logging.info(f"Processing single file at: {file_path}")
    
    try:
        with open(local_file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        logging.error(f"Failed to read file {local_file_path}: {e}")
        raise

    file_paths.append(file_path)

# Create an OpenAI object specifying the endpoint
try:
    openai_client = AzureOpenAI(
        api_key=args.openai_key,
        azure_endpoint=args.openai_endpoint,
        api_version=args.openai_api_version
    )
except Exception as e:
    logging.error(f"Failed to create OpenAI client: {e}")
    raise

# Load encoding locally
try:
    tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception as e:
    logging.error(f"Failed to load tokenizer: {e}")
    raise

def clean_text(text):
    """Clean markdown and HTML from the text."""
    try:
        soup = BeautifulSoup(text, "html.parser")
        text = soup.get_text()
        
        # Remove Markdown URLs
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove Markdown images
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
        
        # Remove remaining Markdown syntax, but keep hyphens
        text = re.sub(r'(?<!\w)[-](?!\w)|[#*_`]+', ' ', text)
        
        # Remove consecutive spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    except Exception as e:
        logging.error(f"Error cleaning text: {e}")
        return ""

def clean_title(title):
    # Decode the title first to handle any URL encoded characters
    title = urllib.parse.unquote(title)
    
    # Replace hyphens and underscores with spaces
    title = title.replace('-', ' ').replace('_', ' ')
    
    # Remove any remaining URL-unsafe characters
    title = re.sub(r'[^\w\s-]', '', title)
    
    # Remove extra whitespace
    title = ' '.join(title.split())
    
    return title

def split_document_by_structure(text, max_tokens, overlap_tokens=50):
    """Split a document into passages by structure with optional overlap."""
    paragraphs = text.split("\n\n")  # Splitting by double newlines to detect paragraphs
    chunks = []
    current_chunk = ""
    current_chunk_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = tokenizer.encode(paragraph)
        
        # If adding this paragraph exceeds the max_tokens limit, create a chunk
        if current_chunk_tokens + len(paragraph_tokens) > max_tokens:
            chunks.append(current_chunk.strip())
            
            # Create a sliding window overlap by taking a portion of the previous chunk
            overlap_chunk = tokenizer.decode(tokenizer.encode(current_chunk)[-overlap_tokens:])
            current_chunk = overlap_chunk  # Start next chunk with the overlap
            current_chunk_tokens = len(tokenizer.encode(current_chunk))
        
        # Add paragraph to the current chunk
        current_chunk += " " + paragraph
        current_chunk_tokens += len(paragraph_tokens)
    
    # Add the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def split_document_into_passages(document, max_tokens=None):
    """Split a document into passages based on token length."""
    try:
        tokens = tokenizer.encode(document)
        if max_tokens is None or len(tokens) <= max_tokens:
            return [document]  # Return the entire document as a single passage
        
        passages = []
        for i in range(0, len(tokens), max_tokens):
            passage_tokens = tokens[i:i + max_tokens]
            passage = tokenizer.decode(passage_tokens)
            passages.append(passage)
            logging.info(f"Processing passage {len(passages)} of {len(tokens) // max_tokens + 1}")
        return passages
    except Exception as e:
        logging.error(f"Error splitting document into passages: {e}")
        return []

def get_text_embedding(text, model=None):
    """Get the embedding for a given text using the specified model."""
    if text.strip() == '':
        logging.warning("Empty text encountered, returning empty embedding.")
        return []
    
    model_name = model if model else args.model_name  # Use the provided argument
    try:
        response = openai_client.embeddings.create(input=[text], model=model_name)
        embedding = response.data[0].embedding
        return embedding
    except OpenAIError as e:
        logging.error(f"OpenAI error: {e}")
        return []
    except Exception as e:
        logging.error(f"Error getting text embedding: {e}")
        return []

def convert_to_azure_search_json(df, key_name='id'):
    """Convert DataFrame to Azure Cognitive Search JSON format."""
    documents = []
    for _, row in df.iterrows():
        # Sanitize the document_id and passage_id before using them
        sanitized_id = sanitize_document_id(f"{row['document_id']}_{row['passage_id']}")
        doc = {
            key_name: sanitized_id,  # Unique ID for the passage
            "content": row['text'],  # Full content of the passage
            "file_path": row['file_path'],  # Original file path
            "title": row['title'],  # Title of the document
            "chunk": int(row['passage_index']),  # The passage chunk index
            "passage_id": int(row['passage_id']),  # Adding passage_id explicitly
            "vector": row['embedding'],  # The vector embedding
            "title_vector": row['title_embedding']  # The title vector embedding
        }
        documents.append(doc)

    return {"value": documents}


def sanitize_document_id(doc_id):
    """Sanitize the document ID by removing invalid characters and avoiding leading underscores."""
    # Replace any invalid characters with an underscore
    sanitized_id = re.sub(r'[^a-zA-Z0-9_\-=]', '_', doc_id)
    
    # Remove any leading underscores
    return sanitized_id.lstrip('_')

def generate_index_definition(index_name, vector_dimension):
    """Generate the index definition for Azure Cognitive Search."""
    return {
        "name": index_name,
        "fields": [
            {
                "name": "id",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,  # ID should be retrievable as a key
                "sortable": False,
                "facetable": False,
                "key": True
            },
            {
                "name": "document_id",  # New field to store the original document ID
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,  # Make the document ID retrievable
                "sortable": False,
                "facetable": False
            },
            {
                "name": "passage_id",  # New field to store the passage ID
                "type": "Edm.Int32",
                "searchable": False,
                "filterable": True,
                "retrievable": True,  # Make passage ID retrievable
                "sortable": False,
                "facetable": False
            },
            {
                "name": "content",
                "type": "Edm.String",
                "searchable": True,  # Allow search in content
                "filterable": False,
                "retrievable": True,  # Make the content field retrievable
                "sortable": False,
                "facetable": False,
                "analyzer": "standard.lucene"
            },
            {
                "name": "file_path",
                "type": "Edm.String",
                "searchable": False,
                "filterable": True,
                "retrievable": True,  # Make the file_path field retrievable
                "sortable": False,
                "facetable": False
            },
            {
                "name": "title",
                "type": "Edm.String",
                "searchable": True,  # Allow search by title
                "filterable": True,  # Filter by title if needed
                "retrievable": True,  # Make title retrievable
                "sortable": False,
                "facetable": False,
                "analyzer": "standard.lucene"
            },
            {
                "name": "chunk",
                "type": "Edm.Int32",
                "searchable": False,
                "filterable": True,  # Filter by chunk if needed
                "retrievable": True,  # Make chunk field retrievable
                "sortable": False,
                "facetable": False
            },
            {
                "name": "vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,  # Vector search requires this field to be searchable
                "filterable": False,
                "retrievable": False,  # Do not make the vector retrievable
                "sortable": False,
                "facetable": False,
                "dimensions": vector_dimension,
                "vectorSearchProfile": "vector-profile-1725439458160"
            },
            {
                "name": "title_vector",
                "type": "Collection(Edm.Single)",
                "searchable": True,  # Allow vector search with title embeddings
                "filterable": False,
                "retrievable": False,  # Do not make title_vector retrievable
                "sortable": False,
                "facetable": False,
                "dimensions": vector_dimension,
                "vectorSearchProfile": "vector-profile-1725439458160"
            }
        ],
        "vectorSearch": {
            "algorithms": [
                {
                    "name": "vector-config-1725439474337",
                    "kind": "hnsw",
                    "hnswParameters": {
                        "metric": "cosine",
                        "m": 4,
                        "efConstruction": 400,
                        "efSearch": 500
                    }
                }
            ],
            "profiles": [
                {
                    "name": "vector-profile-1725439458160",
                    "algorithm": "vector-config-1725439474337"
                }
            ]
        },
        "similarity": {
            "@odata.type": "#Microsoft.Azure.Search.BM25Similarity"
        }
    }

# Main execution
if __name__ == "__main__":
    # Initialize lists to store data
    document_ids, passage_ids, embeddings, texts, titles, title_embeddings, file_paths, passage_indices = [], [], [], [], [], [], [], []

    # Determine files to process
    input_path = args.input
    if os.path.isfile(input_path):
        files_to_process = [input_path]
    elif os.path.isdir(input_path):
        files_to_process = [os.path.join(root, file) for root, _, files in os.walk(input_path) for file in files]
    else:
        raise ValueError(f"Invalid input path: {input_path}")

    total_files = len(files_to_process)

    # Process files
    for file_count, local_file_path in enumerate(files_to_process, 1):
        file_path = get_file_path(local_file_path, args.source_type, args.wiki_url, args.input)
        
        logging.info(f"Processing file {file_count}/{total_files}: {file_path}")
        
        try:
            with open(local_file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            logging.error(f"Failed to read file {local_file_path}: {e}")
            continue
        
        cleaned_text = clean_text(text)
        if not cleaned_text:
            logging.warning(f"Cleaned text from file {file_path} is empty, ignored.")
            continue
        
        try:
            num_tokens = len(tokenizer.encode(cleaned_text))
            logging.info(f"File {file_path} contains {num_tokens} tokens after cleaning")
        except Exception as e:
            logging.error(f"Failed to calculate tokens for file {file_path}: {e}")
            continue
        
        if args.dynamic_chunking:
            document_passages = split_document_by_structure(cleaned_text, args.max_tokens, args.overlap_tokens)
        else:
            document_passages = split_document_into_passages(cleaned_text, args.max_tokens)

        if not document_passages:
            logging.warning(f"No valid passages found for file {file_path}, ignored.")
            continue
        
        title = os.path.splitext(os.path.basename(local_file_path))[0]
        title = clean_title(title)
        if not title.strip():
            title = os.path.splitext(os.path.basename(local_file_path))[0]

        logging.info(f"Cleaned title: {title}")
        title_embedding = get_text_embedding(title, model=args.model_name)
        if not title_embedding:
            logging.warning(f"Failed to get embedding for title: {title}")
        
        logging.info(f"Title: {title}")
        
        # Process passages and store embeddings
        for passage_index, passage in enumerate(document_passages, 1):
            embedding = get_text_embedding(passage, model=args.model_name)
            if embedding:
                document_ids.append(title)
                passage_ids.append(passage_index)
                embeddings.append(embedding)
                texts.append(passage)
                titles.append(title)
                title_embeddings.append(title_embedding)
                file_paths.append(file_path)  # This now contains the correct unique path for each file
                passage_indices.append(passage_index)
                logging.info(f"    Passage {passage_index}/{len(document_passages)} processed")

    # Create DataFrame
    try:
        df = pd.DataFrame({
            'document_id': document_ids,
            'passage_id': passage_ids,
            'file_path': file_paths,
            'passage_index': passage_indices,
            'text': texts,
            'title': titles,
            'title_embedding': title_embeddings,
            'embedding': embeddings
        })
    except Exception as e:
        logging.error(f"Failed to create DataFrame: {e}")
        raise

    # Generate index definition if index_name is provided
    if args.index_name:
        vector_dimension = len(embeddings[0]) if embeddings else 1536
        index_definition = generate_index_definition(args.index_name, vector_dimension)
        index_file = f"{args.output}_index_definition.json"
        with open(index_file, 'w') as f:
            json.dump(index_definition, f, indent=2)
        logging.info(f"\n{'='*50}")
        logging.info(f"INDEX DEFINITION GENERATED")
        logging.info(f"File: {index_file}")
        logging.info(f"{'='*50}\n")
        logging.info(f"Index definition has been written to {index_file}")
    else:
        logging.warning("\nNOTE: No index name provided. Index definition was not generated.")

    # Save the DataFrame based on the chosen output format
    output_file = f"{args.output}.{args.output_format}"
    if args.output_format == 'csv':
        try:
            df.to_csv(output_file, index=False)
            logging.info(f"Embeddings have been successfully written to {output_file}.")
        except Exception as e:
            logging.error(f"Failed to save DataFrame to CSV: {e}")
            raise
    else:  # JSON format
        try:
            json_data = convert_to_azure_search_json(df)
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            logging.info(f"Embeddings have been successfully written to {output_file} in Azure Cognitive Search format.")
        except Exception as e:
            logging.error(f"Failed to save data to JSON: {e}")
            raise

    logging.info("\nScript execution completed.")
    logging.info(f"Output file: {output_file}")
    if args.index_name:
        logging.info(f"Index definition file: {index_file}")
    else:
        logging.info("No index definition file was generated.")
