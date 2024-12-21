-- Enable the vector extension if not already enabled
create extension if not exists vector;

-- Create the embeddings table
create table if not exists embeddings (
    id uuid default gen_random_uuid() primary key,
    user_id text not null,
    agent_id text not null,
    embedding vector(512), -- CLIP ViT-B/32 produces 512-dimensional embeddings
    metadata jsonb,
    embedding_type text not null,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Create indexes for faster queries
create index if not exists embeddings_user_id_idx on embeddings(user_id);
create index if not exists embeddings_agent_id_idx on embeddings(agent_id);
create index if not exists embeddings_embedding_type_idx on embeddings(embedding_type);

-- Create a function to calculate cosine similarity
create or replace function cosine_similarity(a vector, b vector)
returns float
language plpgsql
as $$
begin
    return (a <#> b) * -1 + 1;
end;
$$;

-- Create an index for similarity search
create index if not exists embeddings_embedding_idx on embeddings 
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

-- Create user attributes table for key-value storage
create table if not exists user_attributes (
    id uuid default gen_random_uuid() primary key,
    user_id text not null,
    agent_id text not null,
    key text not null,
    value jsonb not null,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now(),
    constraint unique_user_agent_key unique (user_id, agent_id, key)
);

-- Create indexes for user attributes
create index if not exists user_attributes_user_id_idx on user_attributes(user_id);
create index if not exists user_attributes_agent_id_idx on user_attributes(agent_id);
create index if not exists user_attributes_key_idx on user_attributes(key);