-- Enable the vector extension if not already enabled
create extension if not exists vector;

-- Create the embeddings table
create table if not exists embeddings (
    id uuid default gen_random_uuid() primary key,
    user_id text not null,
    agent_id text not null,
    embedding vector(512), -- CLIP ViT-B/32 produces 512-dimensional embeddings
    embedding_type text not null,
    created_at timestamp with time zone default now()
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

-- Create a function for matching embeddings
create or replace function match_embeddings(
    query_embedding vector(512),
    match_threshold float,
    match_count int
)
returns table (
    id uuid,
    user_id text,
    agent_id text,
    embedding_type text,
    similarity float
)
language plpgsql
as $$
begin
    return query
    select
        e.id,
        e.user_id,
        e.agent_id,
        e.embedding_type,
        cosine_similarity(e.embedding, query_embedding) as similarity
    from embeddings e
    where cosine_similarity(e.embedding, query_embedding) > match_threshold
    order by e.embedding <-> query_embedding
    limit match_count;
end;
$$;

-- Create a function to find similar users
create or replace function find_similar_users(
    target_user_id text,
    embedding_type_filter text default null,
    similarity_threshold float default 0.7,
    max_users int default 10
)
returns table (
    similar_user_id text,
    similarity_score float,
    matching_embeddings int
)
language plpgsql
as $$
begin
    return query
    with target_user_embeddings as (
        select embedding_type, embedding
        from embeddings
        where user_id = target_user_id
        and (embedding_type_filter is null or embedding_type = embedding_type_filter)
    ),
    other_users_embeddings as (
        select distinct e.user_id
        from embeddings e
        where e.user_id != target_user_id
        and (embedding_type_filter is null or e.embedding_type = embedding_type_filter)
    ),
    similarity_scores as (
        select 
            e.user_id,
            avg(cosine_similarity(e.embedding, t.embedding)) as avg_similarity,
            count(*) as match_count
        from target_user_embeddings t
        cross join embeddings e
        where e.user_id != target_user_id
        and e.embedding_type = t.embedding_type
        group by e.user_id
        having avg(cosine_similarity(e.embedding, t.embedding)) > similarity_threshold
    )
    select 
        s.user_id as similar_user_id,
        s.avg_similarity as similarity_score,
        s.match_count as matching_embeddings
    from similarity_scores s
    order by s.avg_similarity desc
    limit max_users;
end;
$$;

-- Create a function to compare two users based on their embeddings
create or replace function compare_users(
    user_id_1 text,
    user_id_2 text,
    embedding_type_filter text default null
)
returns table (
    embedding_type text,
    similarity_score float,
    matching_count int
)
language plpgsql
as $$
begin
    return query
    with user1_embeddings as (
        select embedding_type, array_agg(embedding) as embeddings
        from embeddings
        where user_id = user_id_1
        and (embedding_type_filter is null or embedding_type = embedding_type_filter)
        group by embedding_type
    ),
    user2_embeddings as (
        select embedding_type, array_agg(embedding) as embeddings
        from embeddings
        where user_id = user_id_2
        and (embedding_type_filter is null or embedding_type = embedding_type_filter)
        group by embedding_type
    )
    select 
        coalesce(u1.embedding_type, u2.embedding_type) as embedding_type,
        avg(cosine_similarity(u1_emb.embedding, u2_emb.embedding)) as similarity_score,
        count(*) as matching_count
    from user1_embeddings u1
    join user2_embeddings u2 on u1.embedding_type = u2.embedding_type
    cross join unnest(u1.embeddings) u1_emb
    cross join unnest(u2.embeddings) u2_emb
    group by coalesce(u1.embedding_type, u2.embedding_type);
end;
$$;