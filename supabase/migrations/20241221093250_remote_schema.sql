

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE EXTENSION IF NOT EXISTS "pg_net" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgsodium" WITH SCHEMA "pgsodium";






COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "fuzzystrmatch" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgjwt" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "postgis" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "postgis_tiger_geocoder" WITH SCHEMA "tiger";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."browse_profiles_test"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text", "recent_swipes" "text"[])
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count BIGINT;
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;
  
  -- Count the number of profiles that match the criteria
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
    AND jsonb_array_length(p.photos) > 0;  -- Ensure photos array is not empty

  -- Main query with swipe counts and recent swipes
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('User gender: %s, User preference: %s, Matching profiles: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '), v_count)::TEXT AS debug_info,
    (
      SELECT ARRAY_AGG(s.swipe_type::TEXT ORDER BY s.created_at DESC)
      FROM (
        SELECT 
          s.swipe_type,
          s.created_at
        FROM swipes s
        WHERE s.profile_id = p.id OR s.target_profile_id = p.id
        ORDER BY s.created_at DESC
        LIMIT 5
      ) s
    ) AS recent_swipes
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
    AND jsonb_array_length(p.photos) > 0 
    AND p.is_test = FALSE -- Ensure photos array is not empty
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."browse_profiles_test"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."check_user_exists"("email" "text") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 
    FROM auth.users 
    WHERE email = check_user_exists.email
  );
END;
$$;


ALTER FUNCTION "public"."check_user_exists"("email" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."convert_location_to_geography"("location" "jsonb") RETURNS "extensions"."geography"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
    lat double precision;
    lng double precision;
BEGIN
    -- Handle null case
    IF location IS NULL THEN
        RETURN NULL;
    END IF;

    -- Try to extract coordinates from the first format (with coords object)
    IF location ? 'coords' THEN
        lat := (location->>'coords')::jsonb->>'latitude';
        lng := (location->>'coords')::jsonb->>'longitude';
    -- Try to extract coordinates from the second format (direct lat/lng)
    ELSE
        lat := location->>'latitude';
        lng := location->>'longitude';
    END IF;

    -- If we couldn't extract valid coordinates, return null
    IF lat IS NULL OR lng IS NULL THEN
        RETURN NULL;
    END IF;

    -- Convert to geography point
    -- SRID 4326 is the standard for GPS coordinates (WGS84)
    RETURN ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography;
END;
$$;


ALTER FUNCTION "public"."convert_location_to_geography"("location" "jsonb") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."create_invite_codes"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$DECLARE
  i INTEGER;
BEGIN
  INSERT INTO public.invite_codes (code, profile_id, status)
  VALUES (public.generate_unique_code(), NEW.id, 'active');
  RETURN NEW;
END;$$;


ALTER FUNCTION "public"."create_invite_codes"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."create_user_profile"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    INSERT INTO public.profiles (id, email)
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."create_user_profile"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."delete_message"("message_uuid" "uuid") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    DELETE FROM direct_messages
    WHERE message_id = message_uuid
    AND sender_id = auth.uid();
    
    RETURN FOUND;
END;
$$;


ALTER FUNCTION "public"."delete_message"("message_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."edit_message"("message_uuid" "uuid", "new_content" "text") RETURNS boolean
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    UPDATE direct_messages
    SET 
        content = new_content,
        edited_at = CURRENT_TIMESTAMP
    WHERE message_id = message_uuid
    AND sender_id = auth.uid()
    AND sent_at > NOW() - INTERVAL '5 minutes';
    
    RETURN FOUND;
END;
$$;


ALTER FUNCTION "public"."edit_message"("message_uuid" "uuid", "new_content" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."fetch_profile_with_reclaim"("p_user_id" "uuid") RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "selfie_url" "text", "reclaim_values" "jsonb"[])
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    p.selfie_url,
    ARRAY(
      SELECT jsonb_build_object(
        'provider_id', rpm.provider_id,
        'value', rpm.value,
        'value_type', rpm.value_type
      )
      FROM reclaim_profile_mapping rpm
      WHERE rpm.profile_id = p.id
    ) AS reclaim_values
  FROM profiles p
  WHERE p.id = p_user_id;

END;
$$;


ALTER FUNCTION "public"."fetch_profile_with_reclaim"("p_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."generate_unique_code"() RETURNS "text"
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  generated_code TEXT;
  valid_chars TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
BEGIN
  LOOP
    generated_code := '';
    FOR i IN 1..6 LOOP
      generated_code := generated_code || substr(valid_chars, floor(random() * length(valid_chars) + 1)::integer, 1);
    END LOOP;
    EXIT WHEN NOT EXISTS (SELECT 1 FROM public.invite_codes WHERE invite_codes.code = generated_code);
  END LOOP;
  RETURN generated_code;
END;
$$;


ALTER FUNCTION "public"."generate_unique_code"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."audio_clips" (
    "audio_id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "title" "text" NOT NULL,
    "duration" integer,
    "audio_url" "text",
    "thumbnail_url" "text"
);


ALTER TABLE "public"."audio_clips" OWNER TO "postgres";


COMMENT ON TABLE "public"."audio_clips" IS 'Preset audio_clips';



CREATE OR REPLACE FUNCTION "public"."get_all_audio_clips"() RETURNS SETOF "public"."audio_clips"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY SELECT * FROM audio_clips;
END;
$$;


ALTER FUNCTION "public"."get_all_audio_clips"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_browse_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count INT;
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;

  -- Count the number of profiles that match the criteria
  SELECT COUNT(DISTINCT p.id) INTO v_count
  FROM profiles p
  JOIN swipes s ON s.profile_id = p.id
  WHERE s.target_profile_id = p_user_id
    AND s.is_refunded IS NOT TRUE   -- Exclude refunded swipes
    AND p.id NOT IN (
      SELECT s2.target_profile_id FROM swipes s2 WHERE s2.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference);

  -- Main query with swipe counts
  RETURN QUERY
  SELECT 
    p.id, 
    p.name, 
    p.date_of_birth::DATE,
    p.photos, 
    p.bio, 
    p.email, 
    p.gender, 
    p.gender_preference, 
    p.location, 
    p.is_verified,
    p.cryptonoun,  -- Added cryptonoun field
    -- Number of kisses sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    -- Number of rugs sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    -- Number of kisses received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p.id AND s.target_profile_id = p_user_id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    -- Number of rugs received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p.id AND s.target_profile_id = p_user_id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('User gender: %s, User preference: %s, Matching profiles: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '), v_count)::TEXT AS debug_info
  FROM profiles p
  JOIN swipes s ON s.profile_id = p.id
  WHERE s.target_profile_id = p_user_id
    AND s.is_refunded IS NOT TRUE   -- Exclude refunded swipes
    AND p.id NOT IN (
      SELECT s2.target_profile_id FROM swipes s2 WHERE s2.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
  GROUP BY 
    p.id, p.name, p.date_of_birth, p.photos, p.bio, p.email, p.gender, 
    p.gender_preference, p.location, p.is_verified, p.cryptonoun  -- Include cryptonoun in GROUP BY
  ORDER BY MAX(s.created_at) DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."get_browse_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_browse_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text", "recent_swipes" "text"[], "selfie_url" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count BIGINT;
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;
  
  -- Count the number of profiles that match the criteria
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
    AND jsonb_array_length(p.photos) > 0;

  -- Main query with swipe counts and recent swipes
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('User gender: %s, User preference: %s, Matching profiles: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '), v_count)::TEXT AS debug_info,
    (
      SELECT ARRAY_AGG(s.swipe_type::TEXT ORDER BY s.created_at DESC)
      FROM (
        SELECT 
          s.swipe_type,
          s.created_at
        FROM swipes s
        WHERE s.profile_id = p.id OR s.target_profile_id = p.id
        ORDER BY s.created_at DESC
        LIMIT 5
      ) s
    ) AS recent_swipes,
    p.selfie_url
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
    AND jsonb_array_length(p.photos) > 0
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."get_browse_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_browse_profiles_with_skip"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer, "p_skip_user_id" "uuid") RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text")
    LANGUAGE "plpgsql"
    AS $$DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count INT;
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;

  -- Count the number of profiles that match the criteria
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id != p_skip_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference);

  -- Main query with swipe counts
  RETURN QUERY
  SELECT 
    p.id, 
    p.name, 
    p.date_of_birth::DATE,
    p.photos, 
    p.bio, 
    p.email, 
    p.gender, 
    p.gender_preference, 
    p.location, 
    p.is_verified,
    p.cryptonoun,
    -- Number of kisses sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    -- Number of rugs sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    -- Number of kisses received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p.id AND s.target_profile_id = p_user_id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    -- Number of rugs received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p.id AND s.target_profile_id = p_user_id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('User gender: %s, User preference: %s, Matching profiles: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '), v_count)::TEXT AS debug_info
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id != p_skip_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;$$;


ALTER FUNCTION "public"."get_browse_profiles_with_skip"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer, "p_skip_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_browse_profiles_without_filter"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text", "recent_swipes" "text"[], "selfie_url" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_count BIGINT;
BEGIN
  -- Count all available profiles
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.is_active = true
    AND jsonb_array_length(p.photos) > 0;

  -- Main query
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('Total available profiles: %s', v_count)::TEXT AS debug_info,
    (
      SELECT ARRAY_AGG(s.swipe_type::TEXT ORDER BY s.created_at DESC)
      FROM (
        SELECT 
          s.swipe_type,
          s.created_at
        FROM swipes s
        WHERE s.profile_id = p.id OR s.target_profile_id = p.id
        ORDER BY s.created_at DESC
        LIMIT 5
      ) s
    ) AS recent_swipes,
    p.selfie_url
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.is_active = true
    AND jsonb_array_length(p.photos) > 0
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;

END;
$$;


ALTER FUNCTION "public"."get_browse_profiles_without_filter"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_direct_message"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer DEFAULT 50, "before_timestamp" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS TABLE("message_id" "uuid", "sender_id" "uuid", "recipient_id" "uuid", "content" "text", "sent_at" timestamp with time zone, "status" character varying)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$BEGIN
    RETURN QUERY
    SELECT 
        m.message_id,
        m.sender_id,
        m.recipient_id,
        m.content,
        m.sent_at,
        m.status
    FROM direct_messages m
    WHERE (m.sender_id = user1_uuid AND m.recipient_id = user2_uuid)
       OR (m.sender_id = user2_uuid AND m.recipient_id = user1_uuid)
    AND (before_timestamp IS NULL OR m.sent_at < before_timestamp)
    ORDER BY m.sent_at DESC
    LIMIT page_size;
END;$$;


ALTER FUNCTION "public"."get_direct_message"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_direct_messages"("before_timestamp" timestamp with time zone, "page_size" integer, "user1_uuid" "uuid", "user2_uuid" "uuid") RETURNS TABLE("message_id" "uuid", "sender_id" "uuid", "recipient_id" "uuid", "content" "text", "sent_at" timestamp with time zone, "edited_at" timestamp with time zone, "status" character varying, "metadata" "jsonb", "audio_message_id" "uuid", "message_type" character varying, "audio_id" "uuid", "title" "text", "duration" integer, "audio_url" "text", "thumbnail_url" "text")
    LANGUAGE "plpgsql"
    AS $$
begin
    return query
    select dm.message_id, dm.sender_id, dm.recipient_id, dm.content, dm.sent_at, dm.edited_at, dm.status, dm.metadata, dm.audio_message_id, dm.message_type,
           ac.audio_id, ac.title, ac.duration, ac.audio_url, ac.thumbnail_url
    from direct_messages dm
    left join audio_clips ac on dm.audio_message_id = ac.audio_id
    where (dm.sender_id = user1_uuid and dm.recipient_id = user2_uuid) 
       or (dm.sender_id = user2_uuid and dm.recipient_id = user1_uuid)
       and dm.sent_at < before_timestamp
    order by dm.sent_at desc
    limit page_size;
end;
$$;


ALTER FUNCTION "public"."get_direct_messages"("before_timestamp" timestamp with time zone, "page_size" integer, "user1_uuid" "uuid", "user2_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_direct_messagesr"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer DEFAULT 50, "before_timestamp" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS TABLE("message_id" "uuid", "sender_id" "uuid", "recipient_id" "uuid", "content" "text", "sent_at" timestamp with time zone, "status" character varying)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$BEGIN
    RETURN QUERY
    SELECT 
        m.message_id,
        m.sender_id,
        m.recipient_id,
        m.content,
        m.sent_at,
        m.status
    FROM direct_messages m
    WHERE (m.sender_id = user1_uuid AND m.recipient_id = user2_uuid)
       OR (m.sender_id = user2_uuid AND m.recipient_id = user1_uuid)
    AND (before_timestamp IS NULL OR m.sent_at < before_timestamp)
    ORDER BY m.sent_at DESC
    LIMIT page_size;
END;$$;


ALTER FUNCTION "public"."get_direct_messagesr"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_matched_approved_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "debug_info" "text", "selfie_url" "text")
    LANGUAGE "plpgsql"
    AS $$DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT 
    LOWER(p.gender), 
    ARRAY(SELECT LOWER(UNNEST(p.gender_preference)))
  INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;

  -- Main query
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    format('User gender: %s, User preference: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '))::TEXT AS debug_info,
    p.selfie_url
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      -- Exclude profiles that have existing conversations
      SELECT sender_id FROM direct_messages WHERE recipient_id = p_user_id
      UNION
      SELECT recipient_id FROM direct_messages WHERE sender_id = p_user_id
      UNION
      -- Exclude profiles that the user has reported
      SELECT report_user_id FROM reports WHERE profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    -- Case-insensitive gender preference matching
    AND LOWER(v_user_gender) = ANY(ARRAY(SELECT LOWER(UNNEST(p.gender_preference))))
    AND LOWER(p.gender) = ANY(ARRAY(SELECT LOWER(UNNEST(v_user_gender_preference))))
    AND jsonb_array_length(p.photos) > 0
AND verification_status='approved'
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;$$;


ALTER FUNCTION "public"."get_matched_approved_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_matched_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "debug_info" "text", "selfie_url" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;
    
  -- Main query
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    format('User gender: %s, User preference: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '))::TEXT AS debug_info,
    p.selfie_url
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      -- Exclude profiles that have existing conversations
      SELECT sender_id FROM direct_messages WHERE recipient_id = p_user_id
      UNION
      SELECT recipient_id FROM direct_messages WHERE sender_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
    AND jsonb_array_length(p.photos) > 0
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."get_matched_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "debug_info" "text")
    LANGUAGE "plpgsql"
    AS $$DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
BEGIN
  -- First, retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;

  -- Now use these variables in the main query
  RETURN QUERY
  SELECT 
    p.id, 
    p.name, 
    p.date_of_birth::DATE,
    p.photos, 
    p.bio, 
    p.email, 
    p.gender, 
    p.gender_preference, 
    p.location, 
    p.is_verified,
    format('User gender: %s, User preference: %s', v_user_gender, v_user_gender_preference)::TEXT AS debug_info
  FROM profiles p
  WHERE p.id IN (
    -- Profiles that have swiped on the user
    SELECT s.profile_id
    FROM swipes s
    WHERE s.target_profile_id = p_user_id
  )
  AND p.id NOT IN (
    -- Profiles that the user has swiped on
    SELECT s.target_profile_id
    FROM swipes s
    WHERE s.profile_id = p_user_id
  )
  AND p.gender IS NOT NULL
  AND p.gender_preference IS NOT NULL
  AND array_length(p.gender_preference, 1) > 0
  AND v_user_gender = ANY(p.gender_preference)
  AND p.gender = ANY(v_user_gender_preference)
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;$$;


ALTER FUNCTION "public"."get_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_profiles_and_conversations"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "last_message_time" timestamp with time zone)
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference 
  INTO v_user_gender, v_user_gender_preference
  FROM profiles p 
  WHERE p.id = p_user_id;

  RETURN QUERY
  WITH message_partners AS (
    SELECT DISTINCT
      CASE 
        WHEN sender_profile_id = p_user_id THEN match_id 
        ELSE sender_profile_id 
      END AS profile_id,
      MAX(created_at) as last_message_time
    FROM messages
    WHERE sender_profile_id = p_user_id OR match_id = p_user_id
    GROUP BY 
      CASE 
        WHEN sender_profile_id = p_user_id THEN match_id 
        ELSE sender_profile_id 
      END
  ),
  swipe_stats AS (
    SELECT 
      p.id as profile_id,
      COUNT(*) FILTER (WHERE s.profile_id = p.id AND s.swipe_type = 'kiss')::BIGINT as kisses_sent,
      COUNT(*) FILTER (WHERE s.profile_id = p.id AND s.swipe_type = 'rug')::BIGINT as rugs_sent,
      COUNT(*) FILTER (WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss')::BIGINT as kisses_received,
      COUNT(*) FILTER (WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug')::BIGINT as rugs_received
    FROM profiles p
    LEFT JOIN swipes s ON (s.profile_id = p.id OR s.target_profile_id = p.id)
    GROUP BY p.id
  ),
  active_conversations AS (
    SELECT 
      p.id,
      p.name,
      p.date_of_birth,
      p.photos,
      p.bio,
      p.email,
      p.gender,
      p.gender_preference,
      p.location,
      p.is_verified,
      COALESCE(ss.kisses_sent, 0) as num_of_kisses_sent,
      COALESCE(ss.rugs_sent, 0) as num_of_rugs_sent,
      COALESCE(ss.kisses_received, 0) as num_of_kisses_received,
      COALESCE(ss.rugs_received, 0) as num_of_rugs_received,
      mp.last_message_time
    FROM profiles p
    INNER JOIN message_partners mp ON mp.profile_id = p.id
    LEFT JOIN swipe_stats ss ON ss.profile_id = p.id
    WHERE p.is_active = true
  ),
  potential_matches AS (
    SELECT 
      p.id,
      p.name,
      p.date_of_birth,
      p.photos,
      p.bio,
      p.email,
      p.gender,
      p.gender_preference,
      p.location,
      p.is_verified,
      COALESCE(ss.kisses_sent, 0) as num_of_kisses_sent,
      COALESCE(ss.rugs_sent, 0) as num_of_rugs_sent,
      COALESCE(ss.kisses_received, 0) as num_of_kisses_received,
      COALESCE(ss.rugs_received, 0) as num_of_rugs_received,
      NULL::timestamp with time zone as last_message_time
    FROM profiles p
    LEFT JOIN swipe_stats ss ON ss.profile_id = p.id
    WHERE p.id != p_user_id
      AND p.id NOT IN (SELECT profile_id FROM message_partners)
      AND p.id NOT IN (
        SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
        UNION
        SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
      )
      AND p.is_active = true
      AND p.gender IS NOT NULL
      AND p.gender_preference IS NOT NULL
      AND array_length(p.gender_preference, 1) > 0
      AND v_user_gender = ANY(p.gender_preference)
      AND p.gender = ANY(v_user_gender_preference)
      AND jsonb_array_length(p.photos) > 0
  )
  (
    -- Get ALL active conversations
    SELECT * FROM active_conversations
    ORDER BY last_message_time DESC
  )
  UNION ALL
  (
    -- Get full limit of potential matches
    SELECT * FROM potential_matches
    ORDER BY RANDOM()
    LIMIT p_limit OFFSET p_offset
  );

END;
$$;


ALTER FUNCTION "public"."get_profiles_and_conversations"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_unread_message_count"("user_uuid" "uuid") RETURNS integer
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
    count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO count
    FROM direct_messages
    WHERE recipient_id = user_uuid
    AND status = 'sent';
    
    RETURN count;
END;
$$;


ALTER FUNCTION "public"."get_unread_message_count"("user_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_chats"("user_uuid" "uuid") RETURNS TABLE("other_user_id" "uuid", "other_user_name" character varying, "last_message" "text", "last_message_time" timestamp with time zone, "unread_count" bigint, "other_user_photo" "jsonb")
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$BEGIN
    RETURN QUERY
    WITH LastMessages AS (
        SELECT DISTINCT ON (
            CASE
                WHEN sender_id = user_uuid THEN recipient_id
                ELSE sender_id
            END
        )
            CASE
                WHEN sender_id = user_uuid THEN recipient_id
                ELSE sender_id
            END as other_user_id,
            content as last_message,
            sent_at as last_message_time,
            COUNT(*) FILTER (
                WHERE status = 'sent' 
                AND recipient_id = user_uuid
            ) OVER (
                PARTITION BY CASE
                    WHEN sender_id = user_uuid THEN recipient_id
                    ELSE sender_id
                END
            ) as unread_count
        FROM direct_messages
        WHERE (sender_id = user_uuid 
            OR recipient_id = user_uuid)
        AND CASE
            WHEN sender_id = user_uuid THEN recipient_id
            ELSE sender_id
        END NOT IN (
            -- Exclude users that have been reported by the current user
            SELECT report_user_id 
            FROM reports 
            WHERE profile_id = user_uuid
        )
        ORDER BY other_user_id, sent_at DESC
    )
    SELECT 
        lm.other_user_id,
        p.name::VARCHAR as other_user_name,
        lm.last_message,
        lm.last_message_time,
        lm.unread_count,
        p.photos::JSONB as other_user_photo
    FROM LastMessages lm
    JOIN profiles p ON p.id = lm.other_user_id
    ORDER BY lm.last_message_time DESC NULLS LAST;
END;$$;


ALTER FUNCTION "public"."get_user_chats"("user_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."get_user_profile"("p_user_id" "uuid") RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "selfie_url" "text", "recent_swipes" "text"[])
    LANGUAGE "plpgsql"
    AS $$
BEGIN
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    p.selfie_url,
    (
      SELECT ARRAY_AGG(s.swipe_type::TEXT ORDER BY s.created_at DESC)
      FROM (
        SELECT 
          s.swipe_type,
          s.created_at
        FROM swipes s
        WHERE s.profile_id = p.id OR s.target_profile_id = p.id
        ORDER BY s.created_at DESC
        LIMIT 5
      ) s
    ) AS recent_swipes
  FROM profiles p
  WHERE p.id = p_user_id;
END;
$$;


ALTER FUNCTION "public"."get_user_profile"("p_user_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_new_review"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
begin
    -- Mark any existing pending reviews as discarded
    update profile_reviews
    set 
        review_status = 'discarded',
        reviewed_at = now()
    where 
        profile_id = NEW.profile_id 
        and attribute = NEW.attribute
        and review_status = 'pending'
        and id != NEW.id;
    
    -- Record in history for discarded reviews
    insert into review_history (
        profile_id,
        review_id,
        attribute,
        old_value,
        new_value,
        status,
        metadata
    )
    select 
        profile_id,
        id,
        attribute,
        current_value,
        proposed_value,
        'discarded',
        metadata
    from profile_reviews
    where 
        profile_id = NEW.profile_id 
        and attribute = NEW.attribute
        and review_status = 'pending'
        and id != NEW.id;
    
    return NEW;
end;
$$;


ALTER FUNCTION "public"."handle_new_review"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."handle_updated_at"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."handle_updated_at"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."mark_conversation_messages_read"("other_user_uuid" "uuid") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    UPDATE direct_messages
    SET status = 'read'
    WHERE recipient_id = auth.uid()
    AND sender_id = other_user_uuid
    AND status IN ('sent', 'delivered');
END;
$$;


ALTER FUNCTION "public"."mark_conversation_messages_read"("other_user_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."mark_message_delivered"("message_uuid" "uuid") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    UPDATE direct_messages
    SET status = 'delivered'
    WHERE message_id = message_uuid
    AND recipient_id = auth.uid()
    AND status = 'sent';
END;
$$;


ALTER FUNCTION "public"."mark_message_delivered"("message_uuid" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" "uuid", "name" "text", "date_of_birth" "date", "photos" "jsonb", "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "jsonb", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" bigint, "num_of_rugs_sent" bigint, "num_of_kisses_received" bigint, "num_of_rugs_received" bigint, "debug_info" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count BIGINT;  -- Changed from INT to BIGINT
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;
  
  -- Count the number of profiles that match the criteria
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference);

  -- Main query with swipe counts
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    (SELECT COUNT(*)::BIGINT FROM swipes s WHERE s.target_profile_id = p.id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    format('User gender: %s, User preference: %s, Matching profiles: %s', v_user_gender, ARRAY_TO_STRING(v_user_gender_preference, ', '), v_count)::TEXT AS debug_info
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."match_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."match_profiles_test"("p_user_id" integer, "p_limit" integer, "p_offset" integer) RETURNS TABLE("id" integer, "name" "text", "date_of_birth" "date", "photos" "text"[], "bio" "text", "email" "text", "gender" "text", "gender_preference" "text"[], "location" "text", "is_verified" boolean, "cryptonoun" "text", "num_of_kisses_sent" integer, "num_of_rugs_sent" integer, "num_of_kisses_received" integer, "num_of_rugs_received" integer, "debug_info" "text")
    LANGUAGE "plpgsql"
    AS $$
DECLARE
  v_user_gender TEXT;
  v_user_gender_preference TEXT[];
  v_count INT;
BEGIN
  -- Retrieve the user's gender and gender preference
  SELECT p.gender, p.gender_preference INTO v_user_gender, v_user_gender_preference
  FROM profiles p
  WHERE p.id = p_user_id;
  
  -- Count the number of profiles that match the criteria
  SELECT COUNT(*) INTO v_count
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference);

  -- Main query with swipe counts
  RETURN QUERY
  SELECT
    p.id,
    p.name,
    p.date_of_birth::DATE,
    p.photos,
    p.bio,
    p.email,
    p.gender,
    p.gender_preference,
    p.location,
    p.is_verified,
    p.cryptonoun,
    -- Number of kisses sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.swipe_type = 'kiss') AS num_of_kisses_sent,
    -- Number of rugs sent by user to profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.profile_id = p_user_id AND s.swipe_type = 'rug') AS num_of_rugs_sent,
    -- Number of kisses received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.target_profile_id = p_user_id AND s.swipe_type = 'kiss') AS num_of_kisses_received,
    -- Number of rugs received by user from profile p
    (SELECT COUNT(*) FROM swipes s WHERE s.target_profile_id = p_user_id AND s.swipe_type = 'rug') AS num_of_rugs_received,
    v_count::TEXT AS debug_info
  FROM profiles p
  WHERE p.id != p_user_id
    AND p.id NOT IN (
      SELECT s.profile_id FROM swipes s WHERE s.target_profile_id = p_user_id
      UNION
      SELECT s.target_profile_id FROM swipes s WHERE s.profile_id = p_user_id
    )
    AND p.gender IS NOT NULL
    AND p.is_active = true
    AND p.gender_preference IS NOT NULL
    AND array_length(p.gender_preference, 1) > 0
    AND v_user_gender = ANY(p.gender_preference)
    AND p.gender = ANY(v_user_gender_preference)
  ORDER BY RANDOM()
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


ALTER FUNCTION "public"."match_profiles_test"("p_user_id" integer, "p_limit" integer, "p_offset" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."record_review_completion"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
begin
    if NEW.review_status in ('approved', 'rejected') and 
       OLD.review_status = 'pending' then
        -- Record in history
        insert into review_history (
            profile_id,
            review_id,
            attribute,
            old_value,
            new_value,
            status,
            rejection_reason,
            metadata
        )
        values (
            NEW.profile_id,
            NEW.id,
            NEW.attribute,
            NEW.current_value,
            NEW.proposed_value,
            NEW.review_status,
            NEW.rejection_reason,
            NEW.metadata
        );
    end if;
    return NEW;
end;
$$;


ALTER FUNCTION "public"."record_review_completion"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."send_direct_message"("sender_uuid" "uuid", "recipient_uuid" "uuid", "message_content" "text") RETURNS TABLE("message_id" "uuid", "sender_id" "uuid", "recipient_id" "uuid", "content" "text", "sent_at" timestamp with time zone, "status" character varying)
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    RETURN QUERY
    INSERT INTO direct_messages (
        sender_id,
        recipient_id,
        content
    )
    VALUES (
        sender_uuid,
        recipient_uuid,
        message_content
    )
    RETURNING 
        direct_messages.message_id,
        direct_messages.sender_id,
        direct_messages.recipient_id,
        direct_messages.content,
        direct_messages.sent_at,
        direct_messages.status;
END;
$$;


ALTER FUNCTION "public"."send_direct_message"("sender_uuid" "uuid", "recipient_uuid" "uuid", "message_content" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."send_webhook_local"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  webhook_url TEXT := 'https://optimal-preferably-ladybug.ngrok.app/webhook';
  -- webhook_url TEXT := 'https://backend.kissorrug-968.workers.dev/webhook';
  webhook_secret TEXT;
  payload JSONB;
  signature TEXT;
BEGIN
  -- Retrieve the secret from the vault
  SELECT decrypted_secret INTO webhook_secret
  FROM vault.decrypted_secrets
  WHERE name = 'webhook_secret';

  -- Construct your payload
  payload := jsonb_build_object(
    'event', TG_OP,
    'schema', TG_TABLE_SCHEMA,
    'table', TG_TABLE_NAME,
    'data', CASE
      WHEN TG_OP = 'DELETE' THEN row_to_json(OLD)
      ELSE row_to_json(NEW)
    END
  );

  -- Create HMAC signature using pgcrypto
  signature := encode(extensions.hmac(payload::text, webhook_secret, 'sha256'), 'hex');

  -- Send the webhook using pg_net
  PERFORM net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Webhook-Signature', signature
    ),
    body := payload
  );

  -- For INSERT and UPDATE operations, return NEW; for DELETE, return OLD
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  ELSE
    RETURN NEW;
  END IF;
END;
$$;


ALTER FUNCTION "public"."send_webhook_local"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."send_webhook_prod"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
DECLARE
  -- webhook_url TEXT := 'https://7c22-87-154-214-167.ngrok-free.app/webhook';
  webhook_url TEXT := 'https://backend.kissorrug-968.workers.dev/webhook';
  webhook_secret TEXT;
  payload JSONB;
  signature TEXT;
BEGIN
  -- Retrieve the secret from the vault
  SELECT decrypted_secret INTO webhook_secret
  FROM vault.decrypted_secrets
  WHERE name = 'webhook_secret';

  -- Construct your payload
  payload := jsonb_build_object(
    'event', TG_OP,
    'schema', TG_TABLE_SCHEMA,
    'table', TG_TABLE_NAME,
    'data', CASE
      WHEN TG_OP = 'DELETE' THEN row_to_json(OLD)
      ELSE row_to_json(NEW)
    END
  );

  -- Create HMAC signature using pgcrypto
  signature := encode(extensions.hmac(payload::text, webhook_secret, 'sha256'), 'hex');

  -- Send the webhook using pg_net
  PERFORM net.http_post(
    url := webhook_url,
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'X-Webhook-Signature', signature
    ),
    body := payload
  );

  -- For INSERT and UPDATE operations, return NEW; for DELETE, return OLD
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  ELSE
    RETURN NEW;
  END IF;
END;
$$;


ALTER FUNCTION "public"."send_webhook_prod"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_website_user_onboarded"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
    BEGIN
        UPDATE website_users
        SET is_onboarded = TRUE
        WHERE email = NEW.email;
        RETURN NEW;
    END;
    $$;


ALTER FUNCTION "public"."update_website_user_onboarded"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."verification_status_audit_trigger"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    AS $$
BEGIN
    -- Insert into audit table
    INSERT INTO verification_status_audit (
        profile_id,
        old_status,
        new_status,
        changed_by,
        operation
    )
    VALUES (
        NEW.id,
        OLD.verification_status,
        NEW.verification_status,
        auth.uid(), -- This gets the current user's UUID from Supabase
        TG_OP
    );
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."verification_status_audit_trigger"() OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."activity_logs" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid",
    "activity_type" character varying(50) NOT NULL,
    "activity_details" "text",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ONLY "public"."activity_logs" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."activity_logs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ai_agents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "profile_id" "uuid" DEFAULT "auth"."uid"(),
    "name" "text",
    "symbol" "text",
    "ranking" smallint,
    "market_cap" bigint,
    "profile_image" "text",
    "prompt" "text",
    "truth_index" smallint,
    "interaction_freq" smallint,
    "who_sees_you_prompt" "text",
    "who_you_see_prompt" "text"
);


ALTER TABLE "public"."ai_agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."dashboard_users" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "role" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "created_by" "uuid",
    "is_active" boolean DEFAULT true,
    CONSTRAINT "dashboard_users_role_check" CHECK (("role" = ANY (ARRAY['admin'::"text", 'moderator'::"text"])))
);


ALTER TABLE "public"."dashboard_users" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."direct_messages" (
    "message_id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "sender_id" "uuid",
    "recipient_id" "uuid",
    "content" "text",
    "sent_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "edited_at" timestamp with time zone,
    "status" character varying(20) DEFAULT 'sent'::character varying,
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "audio_message_id" "uuid",
    "message_type" character varying DEFAULT 'text'::character varying NOT NULL
);


ALTER TABLE "public"."direct_messages" OWNER TO "postgres";


COMMENT ON COLUMN "public"."direct_messages"."audio_message_id" IS 'Foreign key for relating audio messages to audio_clips';



COMMENT ON COLUMN "public"."direct_messages"."message_type" IS 'Message type indicating what type of message is this';



CREATE TABLE IF NOT EXISTS "public"."in_app_purchases" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid" NOT NULL,
    "quantity" integer NOT NULL,
    "transaction_raw" "jsonb" NOT NULL,
    "is_sandbox" boolean NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."in_app_purchases" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."invite_codes" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "code" "text" NOT NULL,
    "profile_id" "uuid",
    "status" "text" DEFAULT 'active'::"text"
);


ALTER TABLE "public"."invite_codes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."matches" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile1_id" "uuid",
    "profile2_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ONLY "public"."matches" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."matches" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."matches_v2" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile1_id" "uuid",
    "profile2_id" "uuid",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."matches_v2" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."messages" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "match_id" "uuid",
    "sender_profile_id" "uuid",
    "message_content" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ONLY "public"."messages" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."messages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."onchain_txns" (
    "id" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sender" "text",
    "recipient" "text",
    "swipe_1" "uuid",
    "swipe_2" "uuid",
    "block_number" numeric,
    "usdc_amount" numeric,
    "transaction_fee" numeric,
    "type" "text",
    "status" "text"
);


ALTER TABLE "public"."onchain_txns" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."profile_prompt_responses" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "prompt_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "answer" "text",
    "selected_options" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."profile_prompt_responses" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."profile_prompts" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "question" "text" NOT NULL,
    "answer_type" "text" NOT NULL,
    "options" "jsonb",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."profile_prompts" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."profile_reviews" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid" NOT NULL,
    "attribute" "text" NOT NULL,
    "current_value" "text" NOT NULL,
    "proposed_value" "text" NOT NULL,
    "review_status" "text" DEFAULT 'pending'::"text",
    "rejection_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "reviewed_at" timestamp with time zone,
    "metadata" "jsonb"
);


ALTER TABLE "public"."profile_reviews" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."profiles" (
    "id" "uuid" NOT NULL,
    "name" "text",
    "bio" "text",
    "photos" "jsonb" DEFAULT '[]'::"jsonb",
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "email" "text",
    "gender" "text",
    "date_of_birth" "date",
    "location" "jsonb",
    "gender_preference" "text"[],
    "is_active" boolean DEFAULT true NOT NULL,
    "geographical_location" "extensions"."geography",
    "selfie_url" "text",
    "matching_prompt" "text",
    "verification_status" "text" DEFAULT 'initial_review'::"text",
    "agent_id" "uuid"
);

ALTER TABLE ONLY "public"."profiles" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."profiles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."push_tokens" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "profile_id" "uuid" DEFAULT "auth"."uid"() NOT NULL,
    "push_token" "text" NOT NULL,
    "os" "text" NOT NULL
);


ALTER TABLE "public"."push_tokens" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."reclaim_profile_mapping" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid" NOT NULL,
    "provider_id" "text" NOT NULL,
    "value" "jsonb" NOT NULL,
    "value_type" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."reclaim_profile_mapping" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."reclaim_verifications" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "verification_type" "text" NOT NULL,
    "proof_data" "jsonb" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "verified_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "error_message" "text",
    "context_id" "text",
    "provider_id" "text",
    CONSTRAINT "status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'verified'::"text", 'failed'::"text"])))
);


ALTER TABLE "public"."reclaim_verifications" OWNER TO "postgres";


COMMENT ON TABLE "public"."reclaim_verifications" IS 'Stores verification proofs from Reclaim Protocol';



CREATE TABLE IF NOT EXISTS "public"."reports" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "profile_id" "uuid" DEFAULT "auth"."uid"() NOT NULL,
    "report_user_id" "uuid" NOT NULL,
    "report_reason" "text" NOT NULL
);


ALTER TABLE "public"."reports" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."review_history" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid" NOT NULL,
    "review_id" "uuid" NOT NULL,
    "attribute" "text" NOT NULL,
    "old_value" "text" NOT NULL,
    "new_value" "text" NOT NULL,
    "status" "text" NOT NULL,
    "rejection_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "metadata" "jsonb"
);


ALTER TABLE "public"."review_history" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."swipe_ledger" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "amount" bigint NOT NULL,
    "type" "text" NOT NULL,
    "decision" "text"
);


ALTER TABLE "public"."swipe_ledger" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."swipes" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid",
    "target_profile_id" "uuid",
    "swipe_type" character varying(50) NOT NULL,
    "swipe_cost" numeric(24,12) NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "onchain_settlement" "text",
    "is_refunded" boolean
);

ALTER TABLE ONLY "public"."swipes" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."swipes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."transactions" (
    "id" "uuid" DEFAULT "extensions"."uuid_generate_v4"() NOT NULL,
    "profile_id" "uuid",
    "transaction_type" character varying(50) NOT NULL,
    "amount" numeric(24,12) NOT NULL,
    "status" character varying(50) DEFAULT 'pending'::character varying,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ONLY "public"."transactions" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."transactions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_ai_data" (
    "id" bigint NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "profile_id" "uuid" NOT NULL,
    "agent_id" "uuid" NOT NULL,
    "compatibilty_prompt" "text"
);


ALTER TABLE "public"."user_ai_data" OWNER TO "postgres";


COMMENT ON TABLE "public"."user_ai_data" IS 'This table is has user specific data for each agent';



ALTER TABLE "public"."user_ai_data" ALTER COLUMN "id" ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME "public"."user_agent_map_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



CREATE TABLE IF NOT EXISTS "public"."user_invitations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "inviter_user_id" "uuid" NOT NULL,
    "invited_user_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE "public"."user_invitations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."verification_status_audit" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "profile_id" "uuid",
    "old_status" "text",
    "new_status" "text",
    "changed_by" "uuid",
    "changed_at" timestamp with time zone DEFAULT "now"(),
    "operation" "text"
);


ALTER TABLE "public"."verification_status_audit" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."wallets" (
    "profile_id" "uuid",
    "balance" numeric(24,12) DEFAULT 0.0,
    "wallet_address" character varying(255),
    "created_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "updated_at" timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    "wallet_id" "uuid",
    "id" bigint NOT NULL,
    "wallet_path" "text"
);

ALTER TABLE ONLY "public"."wallets" FORCE ROW LEVEL SECURITY;


ALTER TABLE "public"."wallets" OWNER TO "postgres";


ALTER TABLE "public"."wallets" ALTER COLUMN "id" ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME "public"."wallets_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



CREATE TABLE IF NOT EXISTS "public"."website_users" (
    "id" bigint NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "email" character varying,
    "is_onboarded" boolean DEFAULT false
);


ALTER TABLE "public"."website_users" OWNER TO "postgres";


ALTER TABLE "public"."website_users" ALTER COLUMN "id" ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME "public"."website_users_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ai_agents"
    ADD CONSTRAINT "ai_agents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."audio_clips"
    ADD CONSTRAINT "audio_clips_pkey" PRIMARY KEY ("audio_id");



ALTER TABLE ONLY "public"."dashboard_users"
    ADD CONSTRAINT "dashboard_users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."dashboard_users"
    ADD CONSTRAINT "dashboard_users_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."direct_messages"
    ADD CONSTRAINT "direct_messages_pkey" PRIMARY KEY ("message_id");



ALTER TABLE ONLY "public"."in_app_purchases"
    ADD CONSTRAINT "in_app_purchases_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."invite_codes"
    ADD CONSTRAINT "invite_codes_code_key" UNIQUE ("code");



ALTER TABLE ONLY "public"."invite_codes"
    ADD CONSTRAINT "invite_codes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."matches"
    ADD CONSTRAINT "matches_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."matches_v2"
    ADD CONSTRAINT "matches_v2_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."onchain_txns"
    ADD CONSTRAINT "onchain_txns_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profile_prompt_responses"
    ADD CONSTRAINT "profile_prompt_responses_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profile_prompts"
    ADD CONSTRAINT "profile_prompts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profile_reviews"
    ADD CONSTRAINT "profile_reviews_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."push_tokens"
    ADD CONSTRAINT "push_tokens_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."push_tokens"
    ADD CONSTRAINT "push_tokens_profile_id_key" UNIQUE ("profile_id");



ALTER TABLE ONLY "public"."push_tokens"
    ADD CONSTRAINT "push_tokens_push_token_key" UNIQUE ("push_token");



ALTER TABLE ONLY "public"."reclaim_profile_mapping"
    ADD CONSTRAINT "reclaim_profile_mapping_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."reclaim_verifications"
    ADD CONSTRAINT "reclaim_verifications_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."reports"
    ADD CONSTRAINT "reports_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."review_history"
    ADD CONSTRAINT "review_history_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."swipe_ledger"
    ADD CONSTRAINT "swipe_ledger_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."swipes"
    ADD CONSTRAINT "swipes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."transactions"
    ADD CONSTRAINT "transactions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_invitations"
    ADD CONSTRAINT "unique_invitation" UNIQUE ("invited_user_id");



ALTER TABLE ONLY "public"."user_ai_data"
    ADD CONSTRAINT "user_agent_map_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_invitations"
    ADD CONSTRAINT "user_invitations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."verification_status_audit"
    ADD CONSTRAINT "verification_status_audit_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."wallets"
    ADD CONSTRAINT "wallets_id_key" UNIQUE ("id");



ALTER TABLE ONLY "public"."wallets"
    ADD CONSTRAINT "wallets_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."wallets"
    ADD CONSTRAINT "wallets_wallet_address_key" UNIQUE ("wallet_address");



ALTER TABLE ONLY "public"."website_users"
    ADD CONSTRAINT "website_users_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_dashboard_users_is_active" ON "public"."dashboard_users" USING "btree" ("is_active");



CREATE INDEX "idx_dashboard_users_role" ON "public"."dashboard_users" USING "btree" ("role");



CREATE INDEX "idx_dashboard_users_user_id" ON "public"."dashboard_users" USING "btree" ("user_id");



CREATE INDEX "idx_dm_participants_time" ON "public"."direct_messages" USING "btree" ("sender_id", "recipient_id", "sent_at" DESC);



CREATE INDEX "idx_dm_recipient_time" ON "public"."direct_messages" USING "btree" ("recipient_id", "sent_at" DESC);



CREATE INDEX "idx_dm_sender_time" ON "public"."direct_messages" USING "btree" ("sender_id", "sent_at" DESC);



CREATE INDEX "idx_dm_sent_time" ON "public"."direct_messages" USING "btree" ("sent_at" DESC);



CREATE INDEX "idx_profile_prompt_responses_prompt" ON "public"."profile_prompt_responses" USING "btree" ("prompt_id");



CREATE INDEX "idx_profile_prompt_responses_user" ON "public"."profile_prompt_responses" USING "btree" ("user_id");



CREATE INDEX "idx_profile_reviews_attribute" ON "public"."profile_reviews" USING "btree" ("attribute");



CREATE INDEX "idx_profile_reviews_profile_id" ON "public"."profile_reviews" USING "btree" ("profile_id");



CREATE INDEX "idx_profile_reviews_review_status_created" ON "public"."profile_reviews" USING "btree" ("review_status", "created_at");



CREATE INDEX "idx_profile_reviews_status" ON "public"."profile_reviews" USING "btree" ("profile_id", "review_status");



CREATE INDEX "idx_review_history_profile" ON "public"."review_history" USING "btree" ("profile_id");



CREATE INDEX "idx_review_history_review" ON "public"."review_history" USING "btree" ("review_id");



CREATE INDEX "idx_user_invitations_invited" ON "public"."user_invitations" USING "btree" ("invited_user_id");



CREATE INDEX "idx_user_invitations_inviter" ON "public"."user_invitations" USING "btree" ("inviter_user_id");



CREATE INDEX "reclaim_profile_mapping_profile_id_idx" ON "public"."reclaim_profile_mapping" USING "btree" ("profile_id");



CREATE INDEX "reclaim_profile_mapping_provider_id_idx" ON "public"."reclaim_profile_mapping" USING "btree" ("provider_id");



CREATE INDEX "reclaim_verifications_status_idx" ON "public"."reclaim_verifications" USING "btree" ("status");



CREATE INDEX "reclaim_verifications_user_id_idx" ON "public"."reclaim_verifications" USING "btree" ("user_id");



CREATE OR REPLACE TRIGGER "after_profile_insert" AFTER INSERT ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."update_website_user_onboarded"();

ALTER TABLE "public"."profiles" DISABLE TRIGGER "after_profile_insert";



CREATE OR REPLACE TRIGGER "create_invite_codes_after_profile_insert" AFTER INSERT ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."create_invite_codes"();



CREATE OR REPLACE TRIGGER "create_wallet" AFTER INSERT ON "public"."profiles" FOR EACH ROW EXECUTE FUNCTION "public"."send_webhook_prod"();



CREATE OR REPLACE TRIGGER "discard_previous_reviews" AFTER INSERT ON "public"."profile_reviews" FOR EACH ROW EXECUTE FUNCTION "public"."handle_new_review"();



CREATE OR REPLACE TRIGGER "handle_updated_at" BEFORE UPDATE ON "public"."reclaim_verifications" FOR EACH ROW EXECUTE FUNCTION "public"."handle_updated_at"();



CREATE OR REPLACE TRIGGER "record_review_completion" AFTER UPDATE ON "public"."profile_reviews" FOR EACH ROW EXECUTE FUNCTION "public"."record_review_completion"();



CREATE OR REPLACE TRIGGER "set_updated_at" BEFORE UPDATE ON "public"."dashboard_users" FOR EACH ROW EXECUTE FUNCTION "public"."handle_updated_at"();



CREATE OR REPLACE TRIGGER "sync_swipe_with_smart_contract" AFTER INSERT ON "public"."swipes" FOR EACH ROW EXECUTE FUNCTION "public"."send_webhook_local"();

ALTER TABLE "public"."swipes" DISABLE TRIGGER "sync_swipe_with_smart_contract";



CREATE OR REPLACE TRIGGER "update_user_invitations_updated_at" BEFORE UPDATE ON "public"."user_invitations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "verification_status_change_trigger" AFTER UPDATE OF "verification_status" ON "public"."profiles" FOR EACH ROW WHEN (("old"."verification_status" IS DISTINCT FROM "new"."verification_status")) EXECUTE FUNCTION "public"."verification_status_audit_trigger"();



ALTER TABLE ONLY "public"."activity_logs"
    ADD CONSTRAINT "activity_logs_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ai_agents"
    ADD CONSTRAINT "ai_agents_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."dashboard_users"
    ADD CONSTRAINT "dashboard_users_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."dashboard_users"
    ADD CONSTRAINT "dashboard_users_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."direct_messages"
    ADD CONSTRAINT "direct_messages_audio_message_id_fkey" FOREIGN KEY ("audio_message_id") REFERENCES "public"."audio_clips"("audio_id");



ALTER TABLE ONLY "public"."direct_messages"
    ADD CONSTRAINT "direct_messages_recipient_id_fkey" FOREIGN KEY ("recipient_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."direct_messages"
    ADD CONSTRAINT "direct_messages_sender_id_fkey" FOREIGN KEY ("sender_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."profile_prompt_responses"
    ADD CONSTRAINT "fk_user_profile" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."in_app_purchases"
    ADD CONSTRAINT "in_app_purchases_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."invite_codes"
    ADD CONSTRAINT "invite_codes_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."matches"
    ADD CONSTRAINT "matches_profile1_id_fkey" FOREIGN KEY ("profile1_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."matches"
    ADD CONSTRAINT "matches_profile2_id_fkey" FOREIGN KEY ("profile2_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."matches_v2"
    ADD CONSTRAINT "matches_v2_profile1_id_fkey" FOREIGN KEY ("profile1_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."matches_v2"
    ADD CONSTRAINT "matches_v2_profile2_id_fkey" FOREIGN KEY ("profile2_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_match_id_fkey" FOREIGN KEY ("match_id") REFERENCES "public"."matches"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."messages"
    ADD CONSTRAINT "messages_sender_profile_id_fkey" FOREIGN KEY ("sender_profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."onchain_txns"
    ADD CONSTRAINT "onchain_txns_recipient_fkey" FOREIGN KEY ("recipient") REFERENCES "public"."wallets"("wallet_address");



ALTER TABLE ONLY "public"."onchain_txns"
    ADD CONSTRAINT "onchain_txns_sender_fkey" FOREIGN KEY ("sender") REFERENCES "public"."wallets"("wallet_address");



ALTER TABLE ONLY "public"."onchain_txns"
    ADD CONSTRAINT "onchain_txns_swipe_1_fkey" FOREIGN KEY ("swipe_1") REFERENCES "public"."swipes"("id");



ALTER TABLE ONLY "public"."onchain_txns"
    ADD CONSTRAINT "onchain_txns_swipe_2_fkey" FOREIGN KEY ("swipe_2") REFERENCES "public"."swipes"("id");



ALTER TABLE ONLY "public"."profile_prompt_responses"
    ADD CONSTRAINT "profile_prompt_responses_prompt_id_fkey" FOREIGN KEY ("prompt_id") REFERENCES "public"."profile_prompts"("id");



ALTER TABLE ONLY "public"."profile_reviews"
    ADD CONSTRAINT "profile_reviews_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."ai_agents"("id");



ALTER TABLE ONLY "public"."profiles"
    ADD CONSTRAINT "profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."push_tokens"
    ADD CONSTRAINT "push_tokens_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."reclaim_profile_mapping"
    ADD CONSTRAINT "reclaim_profile_mapping_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."reclaim_profile_mapping"
    ADD CONSTRAINT "reclaim_profile_mapping_profile_id_fkey1" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."reclaim_verifications"
    ADD CONSTRAINT "reclaim_verifications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."reports"
    ADD CONSTRAINT "reports_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."review_history"
    ADD CONSTRAINT "review_history_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."review_history"
    ADD CONSTRAINT "review_history_review_id_fkey" FOREIGN KEY ("review_id") REFERENCES "public"."profile_reviews"("id");



ALTER TABLE ONLY "public"."swipe_ledger"
    ADD CONSTRAINT "swipe_ledger_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."swipes"
    ADD CONSTRAINT "swipes_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."swipes"
    ADD CONSTRAINT "swipes_target_profile_id_fkey" FOREIGN KEY ("target_profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."transactions"
    ADD CONSTRAINT "transactions_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_ai_data"
    ADD CONSTRAINT "user_agent_map_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "public"."ai_agents"("id");



ALTER TABLE ONLY "public"."user_ai_data"
    ADD CONSTRAINT "user_agent_map_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."user_invitations"
    ADD CONSTRAINT "user_invitations_invited_user_id_fkey" FOREIGN KEY ("invited_user_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."user_invitations"
    ADD CONSTRAINT "user_invitations_inviter_user_id_fkey" FOREIGN KEY ("inviter_user_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."verification_status_audit"
    ADD CONSTRAINT "verification_status_audit_changed_by_fkey" FOREIGN KEY ("changed_by") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."verification_status_audit"
    ADD CONSTRAINT "verification_status_audit_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id");



ALTER TABLE ONLY "public"."wallets"
    ADD CONSTRAINT "wallets_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE CASCADE;



CREATE POLICY "Allow Authenticated Users to Insert" ON "public"."profiles" FOR INSERT TO "authenticated" WITH CHECK (("auth"."role"() = 'authenticated'::"text"));



CREATE POLICY "Allow authenticated users to view audio clips" ON "public"."audio_clips" FOR SELECT USING (true);



CREATE POLICY "Allow everybody to view profiles" ON "public"."profiles" FOR SELECT USING (true);



CREATE POLICY "Allow read access to all profile prompts" ON "public"."profile_prompts" FOR SELECT TO "authenticated" USING (true);



CREATE POLICY "Allow updates except id" ON "public"."profiles" FOR UPDATE USING (("auth"."uid"() = "id")) WITH CHECK (("id" = "auth"."uid"()));



CREATE POLICY "Allow user to insert messages in their matches" ON "public"."messages" FOR INSERT WITH CHECK ((("auth"."uid"() = "sender_profile_id") AND (EXISTS ( SELECT 1
   FROM "public"."matches"
  WHERE (("matches"."id" = "messages"."match_id") AND (("matches"."profile1_id" = "auth"."uid"()) OR ("matches"."profile2_id" = "auth"."uid"())))))));



CREATE POLICY "Allow user to view messages in their matches" ON "public"."messages" FOR SELECT USING ((("auth"."uid"() IN ( SELECT "matches"."profile1_id"
   FROM "public"."matches"
  WHERE ("matches"."id" = "messages"."match_id"))) OR ("auth"."uid"() IN ( SELECT "matches"."profile2_id"
   FROM "public"."matches"
  WHERE ("matches"."id" = "messages"."match_id")))));



CREATE POLICY "Allow user to view their own activity logs" ON "public"."activity_logs" FOR SELECT USING (("auth"."uid"() = "profile_id"));



CREATE POLICY "Allow user to view their own matches" ON "public"."matches" FOR SELECT USING ((("auth"."uid"() = "profile1_id") OR ("auth"."uid"() = "profile2_id")));



CREATE POLICY "Allow user to view their own swipes" ON "public"."swipes" FOR SELECT USING ((("auth"."uid"() = "profile_id") OR ("auth"."uid"() = "target_profile_id")));



CREATE POLICY "Allow user to view their own transactions" ON "public"."transactions" FOR SELECT USING (("auth"."uid"() = "profile_id"));



CREATE POLICY "Allow user to view their own wallet" ON "public"."wallets" FOR SELECT USING (("auth"."uid"() = "profile_id"));



CREATE POLICY "Allow users to update their own profile" ON "public"."profiles" FOR UPDATE TO "authenticated" USING (("auth"."uid"() = "id")) WITH CHECK (("auth"."uid"() = "id"));



CREATE POLICY "Dashboard users can view dashboard_users" ON "public"."dashboard_users" FOR SELECT TO "authenticated" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Enable delete for users based on user_id" ON "public"."reclaim_profile_mapping" FOR DELETE USING ((( SELECT "auth"."uid"() AS "uid") = "profile_id"));



CREATE POLICY "Enable insert for users based on user_id" ON "public"."invite_codes" FOR INSERT WITH CHECK ((( SELECT "auth"."uid"() AS "uid") = "profile_id"));



CREATE POLICY "Enable insert for users based on user_id" ON "public"."reports" FOR INSERT WITH CHECK ((( SELECT "auth"."uid"() AS "uid") = "profile_id"));



CREATE POLICY "Enable insert for users based on user_id" ON "public"."review_history" FOR INSERT WITH CHECK (("profile_id" = "auth"."uid"()));



CREATE POLICY "Enable insert for users based on user_id" ON "public"."user_invitations" FOR INSERT WITH CHECK ((( SELECT "auth"."uid"() AS "uid") = "invited_user_id"));



CREATE POLICY "Enable read access for all users" ON "public"."invite_codes" FOR SELECT USING (true);



CREATE POLICY "Only admins can update reviews" ON "public"."profile_reviews" FOR UPDATE USING ((("auth"."jwt"() ->> 'role'::"text") = 'admin'::"text"));



CREATE POLICY "Recipients can update message status" ON "public"."direct_messages" FOR UPDATE USING ((("auth"."uid"() = "recipient_id") AND ("sender_id" = "sender_id") AND ("recipient_id" = "recipient_id") AND ("content" = "content")));



CREATE POLICY "Users can create their own reviews" ON "public"."profile_reviews" FOR INSERT WITH CHECK (("profile_id" = "auth"."uid"()));



CREATE POLICY "Users can delete their sent messages" ON "public"."direct_messages" FOR DELETE USING (("auth"."uid"() = "sender_id"));



CREATE POLICY "Users can edit recent messages" ON "public"."direct_messages" FOR UPDATE USING ((("auth"."uid"() = "sender_id") AND ("sent_at" > ("now"() - '00:05:00'::interval))));



CREATE POLICY "Users can insert own mapping data" ON "public"."reclaim_profile_mapping" FOR INSERT WITH CHECK (("auth"."uid"() = "profile_id"));



CREATE POLICY "Users can send messages" ON "public"."direct_messages" FOR INSERT WITH CHECK (("auth"."uid"() = "sender_id"));



CREATE POLICY "Users can update own mapping data" ON "public"."reclaim_profile_mapping" FOR UPDATE USING (("auth"."uid"() = "profile_id"));



CREATE POLICY "Users can view own mapping data" ON "public"."reclaim_profile_mapping" FOR SELECT USING (("auth"."uid"() = "profile_id"));



CREATE POLICY "Users can view responses about them" ON "public"."profile_prompt_responses" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own history" ON "public"."review_history" FOR SELECT USING (("profile_id" = "auth"."uid"()));



CREATE POLICY "Users can view their own messages" ON "public"."direct_messages" FOR SELECT USING ((("auth"."uid"() = "sender_id") OR ("auth"."uid"() = "recipient_id")));



CREATE POLICY "Users can view their own reviews" ON "public"."profile_reviews" FOR SELECT USING (("profile_id" = "auth"."uid"()));



ALTER TABLE "public"."activity_logs" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ai_agents" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "all for own" ON "public"."push_tokens" USING ((( SELECT "auth"."uid"() AS "uid") = "profile_id"));



ALTER TABLE "public"."audio_clips" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."dashboard_users" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."direct_messages" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."in_app_purchases" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."invite_codes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."matches" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."matches_v2" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."messages" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."onchain_txns" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."profile_prompt_responses" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."profile_prompts" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."profile_reviews" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."profiles" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."push_tokens" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."reclaim_profile_mapping" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."reclaim_verifications" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."reports" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."review_history" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."swipe_ledger" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."swipes" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."transactions" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "update_own_profile" ON "public"."profile_reviews" FOR UPDATE USING (("profile_id" = "auth"."uid"())) WITH CHECK (("profile_id" = "auth"."uid"()));



ALTER TABLE "public"."user_ai_data" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_invitations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."wallets" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."website_users" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."direct_messages";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."profile_reviews";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."review_history";






GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";





























































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































GRANT ALL ON FUNCTION "public"."browse_profiles_test"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."browse_profiles_test"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."browse_profiles_test"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."check_user_exists"("email" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."check_user_exists"("email" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."check_user_exists"("email" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."convert_location_to_geography"("location" "jsonb") TO "anon";
GRANT ALL ON FUNCTION "public"."convert_location_to_geography"("location" "jsonb") TO "authenticated";
GRANT ALL ON FUNCTION "public"."convert_location_to_geography"("location" "jsonb") TO "service_role";



GRANT ALL ON FUNCTION "public"."create_invite_codes"() TO "anon";
GRANT ALL ON FUNCTION "public"."create_invite_codes"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."create_invite_codes"() TO "service_role";



GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "anon";
GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "service_role";



GRANT ALL ON FUNCTION "public"."delete_message"("message_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."delete_message"("message_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."delete_message"("message_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."edit_message"("message_uuid" "uuid", "new_content" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."edit_message"("message_uuid" "uuid", "new_content" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."edit_message"("message_uuid" "uuid", "new_content" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."fetch_profile_with_reclaim"("p_user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."fetch_profile_with_reclaim"("p_user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."fetch_profile_with_reclaim"("p_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."generate_unique_code"() TO "anon";
GRANT ALL ON FUNCTION "public"."generate_unique_code"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."generate_unique_code"() TO "service_role";



GRANT ALL ON TABLE "public"."audio_clips" TO "anon";
GRANT ALL ON TABLE "public"."audio_clips" TO "authenticated";
GRANT ALL ON TABLE "public"."audio_clips" TO "service_role";



GRANT ALL ON FUNCTION "public"."get_all_audio_clips"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_all_audio_clips"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_all_audio_clips"() TO "service_role";



GRANT ALL ON FUNCTION "public"."get_browse_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_browse_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_browse_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_browse_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_browse_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_browse_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_browse_profiles_with_skip"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer, "p_skip_user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_browse_profiles_with_skip"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer, "p_skip_user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_browse_profiles_with_skip"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer, "p_skip_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_browse_profiles_without_filter"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_browse_profiles_without_filter"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_browse_profiles_without_filter"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_direct_message"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."get_direct_message"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_direct_message"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_direct_messages"("before_timestamp" timestamp with time zone, "page_size" integer, "user1_uuid" "uuid", "user2_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_direct_messages"("before_timestamp" timestamp with time zone, "page_size" integer, "user1_uuid" "uuid", "user2_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_direct_messages"("before_timestamp" timestamp with time zone, "page_size" integer, "user1_uuid" "uuid", "user2_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_direct_messagesr"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."get_direct_messagesr"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_direct_messagesr"("user1_uuid" "uuid", "user2_uuid" "uuid", "page_size" integer, "before_timestamp" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_matched_approved_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_matched_approved_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_matched_approved_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_matched_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_matched_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_matched_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_my_turn_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_profiles_and_conversations"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."get_profiles_and_conversations"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_profiles_and_conversations"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."get_unread_message_count"("user_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_unread_message_count"("user_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_unread_message_count"("user_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_chats"("user_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_chats"("user_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_chats"("user_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."get_user_profile"("p_user_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_user_profile"("p_user_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_user_profile"("p_user_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_new_review"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_new_review"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_new_review"() TO "service_role";



GRANT ALL ON FUNCTION "public"."handle_updated_at"() TO "anon";
GRANT ALL ON FUNCTION "public"."handle_updated_at"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."handle_updated_at"() TO "service_role";



GRANT ALL ON FUNCTION "public"."mark_conversation_messages_read"("other_user_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."mark_conversation_messages_read"("other_user_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."mark_conversation_messages_read"("other_user_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."mark_message_delivered"("message_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."mark_message_delivered"("message_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."mark_message_delivered"("message_uuid" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."match_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_profiles"("p_user_id" "uuid", "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."match_profiles_test"("p_user_id" integer, "p_limit" integer, "p_offset" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."match_profiles_test"("p_user_id" integer, "p_limit" integer, "p_offset" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."match_profiles_test"("p_user_id" integer, "p_limit" integer, "p_offset" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."record_review_completion"() TO "anon";
GRANT ALL ON FUNCTION "public"."record_review_completion"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."record_review_completion"() TO "service_role";



GRANT ALL ON FUNCTION "public"."send_direct_message"("sender_uuid" "uuid", "recipient_uuid" "uuid", "message_content" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."send_direct_message"("sender_uuid" "uuid", "recipient_uuid" "uuid", "message_content" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."send_direct_message"("sender_uuid" "uuid", "recipient_uuid" "uuid", "message_content" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."send_webhook_local"() TO "anon";
GRANT ALL ON FUNCTION "public"."send_webhook_local"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."send_webhook_local"() TO "service_role";



GRANT ALL ON FUNCTION "public"."send_webhook_prod"() TO "anon";
GRANT ALL ON FUNCTION "public"."send_webhook_prod"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."send_webhook_prod"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";



GRANT ALL ON FUNCTION "public"."update_website_user_onboarded"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_website_user_onboarded"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_website_user_onboarded"() TO "service_role";



GRANT ALL ON FUNCTION "public"."verification_status_audit_trigger"() TO "anon";
GRANT ALL ON FUNCTION "public"."verification_status_audit_trigger"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."verification_status_audit_trigger"() TO "service_role";
















































































































































































































































GRANT ALL ON TABLE "public"."activity_logs" TO "anon";
GRANT ALL ON TABLE "public"."activity_logs" TO "authenticated";
GRANT ALL ON TABLE "public"."activity_logs" TO "service_role";



GRANT ALL ON TABLE "public"."ai_agents" TO "anon";
GRANT ALL ON TABLE "public"."ai_agents" TO "authenticated";
GRANT ALL ON TABLE "public"."ai_agents" TO "service_role";



GRANT ALL ON TABLE "public"."dashboard_users" TO "anon";
GRANT ALL ON TABLE "public"."dashboard_users" TO "authenticated";
GRANT ALL ON TABLE "public"."dashboard_users" TO "service_role";



GRANT ALL ON TABLE "public"."direct_messages" TO "anon";
GRANT ALL ON TABLE "public"."direct_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."direct_messages" TO "service_role";



GRANT ALL ON TABLE "public"."in_app_purchases" TO "anon";
GRANT ALL ON TABLE "public"."in_app_purchases" TO "authenticated";
GRANT ALL ON TABLE "public"."in_app_purchases" TO "service_role";



GRANT ALL ON TABLE "public"."invite_codes" TO "anon";
GRANT ALL ON TABLE "public"."invite_codes" TO "authenticated";
GRANT ALL ON TABLE "public"."invite_codes" TO "service_role";



GRANT ALL ON TABLE "public"."matches" TO "anon";
GRANT ALL ON TABLE "public"."matches" TO "authenticated";
GRANT ALL ON TABLE "public"."matches" TO "service_role";



GRANT ALL ON TABLE "public"."matches_v2" TO "anon";
GRANT ALL ON TABLE "public"."matches_v2" TO "authenticated";
GRANT ALL ON TABLE "public"."matches_v2" TO "service_role";



GRANT ALL ON TABLE "public"."messages" TO "anon";
GRANT ALL ON TABLE "public"."messages" TO "authenticated";
GRANT ALL ON TABLE "public"."messages" TO "service_role";



GRANT ALL ON TABLE "public"."onchain_txns" TO "anon";
GRANT ALL ON TABLE "public"."onchain_txns" TO "authenticated";
GRANT ALL ON TABLE "public"."onchain_txns" TO "service_role";



GRANT ALL ON TABLE "public"."profile_prompt_responses" TO "anon";
GRANT ALL ON TABLE "public"."profile_prompt_responses" TO "authenticated";
GRANT ALL ON TABLE "public"."profile_prompt_responses" TO "service_role";



GRANT ALL ON TABLE "public"."profile_prompts" TO "anon";
GRANT ALL ON TABLE "public"."profile_prompts" TO "authenticated";
GRANT ALL ON TABLE "public"."profile_prompts" TO "service_role";



GRANT ALL ON TABLE "public"."profile_reviews" TO "anon";
GRANT ALL ON TABLE "public"."profile_reviews" TO "authenticated";
GRANT ALL ON TABLE "public"."profile_reviews" TO "service_role";



GRANT ALL ON TABLE "public"."profiles" TO "anon";
GRANT ALL ON TABLE "public"."profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."profiles" TO "service_role";



GRANT ALL ON TABLE "public"."push_tokens" TO "anon";
GRANT ALL ON TABLE "public"."push_tokens" TO "authenticated";
GRANT ALL ON TABLE "public"."push_tokens" TO "service_role";



GRANT ALL ON TABLE "public"."reclaim_profile_mapping" TO "anon";
GRANT ALL ON TABLE "public"."reclaim_profile_mapping" TO "authenticated";
GRANT ALL ON TABLE "public"."reclaim_profile_mapping" TO "service_role";



GRANT ALL ON TABLE "public"."reclaim_verifications" TO "anon";
GRANT ALL ON TABLE "public"."reclaim_verifications" TO "authenticated";
GRANT ALL ON TABLE "public"."reclaim_verifications" TO "service_role";



GRANT ALL ON TABLE "public"."reports" TO "anon";
GRANT ALL ON TABLE "public"."reports" TO "authenticated";
GRANT ALL ON TABLE "public"."reports" TO "service_role";



GRANT ALL ON TABLE "public"."review_history" TO "anon";
GRANT ALL ON TABLE "public"."review_history" TO "authenticated";
GRANT ALL ON TABLE "public"."review_history" TO "service_role";



GRANT ALL ON TABLE "public"."swipe_ledger" TO "anon";
GRANT ALL ON TABLE "public"."swipe_ledger" TO "authenticated";
GRANT ALL ON TABLE "public"."swipe_ledger" TO "service_role";



GRANT ALL ON TABLE "public"."swipes" TO "anon";
GRANT ALL ON TABLE "public"."swipes" TO "authenticated";
GRANT ALL ON TABLE "public"."swipes" TO "service_role";



GRANT ALL ON TABLE "public"."transactions" TO "anon";
GRANT ALL ON TABLE "public"."transactions" TO "authenticated";
GRANT ALL ON TABLE "public"."transactions" TO "service_role";



GRANT ALL ON TABLE "public"."user_ai_data" TO "anon";
GRANT ALL ON TABLE "public"."user_ai_data" TO "authenticated";
GRANT ALL ON TABLE "public"."user_ai_data" TO "service_role";



GRANT ALL ON SEQUENCE "public"."user_agent_map_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."user_agent_map_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."user_agent_map_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."user_invitations" TO "anon";
GRANT ALL ON TABLE "public"."user_invitations" TO "authenticated";
GRANT ALL ON TABLE "public"."user_invitations" TO "service_role";



GRANT ALL ON TABLE "public"."verification_status_audit" TO "anon";
GRANT ALL ON TABLE "public"."verification_status_audit" TO "authenticated";
GRANT ALL ON TABLE "public"."verification_status_audit" TO "service_role";



GRANT ALL ON TABLE "public"."wallets" TO "anon";
GRANT ALL ON TABLE "public"."wallets" TO "authenticated";
GRANT ALL ON TABLE "public"."wallets" TO "service_role";



GRANT ALL ON SEQUENCE "public"."wallets_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."wallets_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."wallets_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."website_users" TO "anon";
GRANT ALL ON TABLE "public"."website_users" TO "authenticated";
GRANT ALL ON TABLE "public"."website_users" TO "service_role";



GRANT ALL ON SEQUENCE "public"."website_users_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."website_users_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."website_users_id_seq" TO "service_role";

























































































































































ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS  TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES  TO "service_role";






























RESET ALL;
