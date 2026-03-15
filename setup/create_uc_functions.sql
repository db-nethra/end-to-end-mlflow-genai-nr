-- UC Functions for DC Assistant
-- Generated from 02_FunctionDefinition.py
-- The setup script replaces {CATALOG} and {SCHEMA} with actual values before execution.

-- Function 1
CREATE OR REPLACE FUNCTION tendencies_by_offense_formation(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for (e.g., array(2023,2024))',
  redzone BOOLEAN COMMENT 'If TRUE, restrict to red zone plays (yardline_100 <= 20); if NULL/false, include all'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive formation tendencies with parsed personnel buckets'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards
      )
    )
  )
  FROM (
    SELECT
      offense_formation,
      personnel_bucket,
      COUNT(*) AS plays,
      SUM(pass_plays) AS pass_plays,
      SUM(rush_plays) AS rush_plays,
      SUM(pass_plays) / COUNT(*) AS pass_rate,
      SUM(rush_plays) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(CAST(success AS DOUBLE)) AS success_rate,
      AVG(yards_gained) AS avg_yards
    FROM (
      SELECT
        a.offense_formation,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket,
        p.play_type,
        CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END AS pass_plays,
        CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END AS rush_plays,
        p.epa,
        p.success,
        p.yards_gained
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND p.play_type IN ('pass', 'run')
        AND (redzone IS NULL OR redzone = FALSE OR p.yardline_100 <= 20)
    )
    GROUP BY offense_formation, personnel_bucket
    ORDER BY plays DESC, offense_formation, personnel_bucket
    LIMIT 100
  )
);

-- COMMAND ----------
-- Down & distance tendencies (offense-only table function)
CREATE OR REPLACE FUNCTION tendencies_by_down_distance(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  redzone BOOLEAN COMMENT 'If TRUE, restrict to red zone plays (yardline_100 <= 20); if NULL/false, include all'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive down & distance tendencies for a team'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'down', down,
        'distance_bucket', distance_bucket,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      down,
      distance_bucket,
      COUNT(*) AS plays,
      SUM(pass_plays) AS pass_plays,
      SUM(rush_plays) AS rush_plays,
      SUM(pass_plays) / COUNT(*) AS pass_rate,
      SUM(rush_plays) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(CAST(success AS DOUBLE)) AS success_rate,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.down,
        CASE
          WHEN p.ydstogo <= 2 THEN '1-2'
          WHEN p.ydstogo <= 6 THEN '3-6'
          WHEN p.ydstogo <= 10 THEN '7-10'
          ELSE '>10'
        END AS distance_bucket,
        p.play_type,
        CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END AS pass_plays,
        CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END AS rush_plays,
        p.epa,
        p.success,
        p.yards_gained,
        p.air_yards,
        p.yards_after_catch,
        p.first_down
      FROM football_pbp_data p
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND p.down IS NOT NULL
        AND p.play_type IN ('pass', 'run')
        AND (redzone IS NULL OR redzone = FALSE OR p.yardline_100 <= 20)
    )
    GROUP BY down, distance_bucket
    ORDER BY down, distance_bucket
    LIMIT 100
  )
);


-- COMMAND ----------
-- Who got the ball given situation (offense-only, filters include formation & personnel bucket)
CREATE OR REPLACE FUNCTION who_got_ball_by_offense_situation(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  offense_formation STRING COMMENT 'Offensive formation to filter by',
  personnel_bucket STRING COMMENT 'Parsed personnel bucket string (e.g., "5 OL, 1 RB, 1 TE, 3 WR, 1 QB")',
  down INT COMMENT 'Down to filter by (1-4)',
  distance_bucket STRING COMMENT 'Distance bucket to filter by: 1-2|3-6|7-10|>10',
  redzone BOOLEAN COMMENT 'If TRUE, restrict to red zone plays (yardline_100 <= 20); if NULL/false, include all'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: who got the ball (receiver on passes, rusher on runs) for a given formation, personnel, down and distance bucket'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'ball_getter', ball_getter,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      ball_getter,
      COUNT(*) AS plays,
      SUM(pass_plays) AS pass_plays,
      SUM(rush_plays) AS rush_plays,
      SUM(pass_plays) / COUNT(*) AS pass_rate,
      SUM(rush_plays) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.play_id,
        p.down,
        CASE
          WHEN p.ydstogo <= 2 THEN '1-2'
          WHEN p.ydstogo <= 6 THEN '3-6'
          WHEN p.ydstogo <= 10 THEN '7-10'
          ELSE '>10'
        END AS distance_bucket_calc,
        a.offense_formation,
        CONCAT(
          CAST(GREATEST(0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket_calc,
        CASE
          WHEN CAST(p.`pass` AS DOUBLE) = 1 THEN p.receiver
          WHEN CAST(p.rush AS DOUBLE) = 1 THEN p.rusher
          ELSE 'UNKNOWN'
        END AS ball_getter,
        p.posteam,
        p.season,
        p.play_type,
        CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END AS pass_plays,
        CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END AS rush_plays,
        p.epa,
        p.yards_gained,
        p.first_down,
        p.air_yards,
        p.yards_after_catch
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2022, 2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND p.play_type IN ('pass', 'run')
        AND (redzone IS NULL OR redzone = FALSE OR p.yardline_100 <= 20)
    ) s
    WHERE s.offense_formation = offense_formation
      AND s.personnel_bucket_calc = personnel_bucket
      AND s.down = down
      AND s.distance_bucket_calc = distance_bucket
    GROUP BY ball_getter
    ORDER BY plays DESC
    LIMIT 100
  )
);


-- COMMAND ----------
-- Who got the ball by down & distance and formation (no formation/personnel inputs; grouped by them)
CREATE OR REPLACE FUNCTION who_got_ball_by_down_distance_and_form(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  down INT COMMENT 'Down to filter by (1-4)',
  distance_bucket STRING COMMENT 'Distance bucket to filter by: 1-2|3-6|7-10|>10',
  redzone BOOLEAN COMMENT 'If TRUE, restrict to red zone plays (yardline_100 <= 20); if NULL/false, include all'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: for a down+distance bucket, list who got the ball grouped by offense_formation and personnel bucket'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'ball_getter', ball_getter,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      offense_formation,
      personnel_bucket,
      ball_getter,
      COUNT(*) AS plays,
      SUM(pass_plays) AS pass_plays,
      SUM(rush_plays) AS rush_plays,
      SUM(pass_plays) / COUNT(*) AS pass_rate,
      SUM(rush_plays) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.play_id,
        p.down,
        CASE
          WHEN p.ydstogo <= 2 THEN '1-2'
          WHEN p.ydstogo <= 6 THEN '3-6'
          WHEN p.ydstogo <= 10 THEN '7-10'
          ELSE '>10'
        END AS distance_bucket_calc,
        a.offense_formation,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket,
        CASE
          WHEN CAST(p.`pass` AS DOUBLE) = 1 THEN p.receiver
          WHEN CAST(p.rush AS DOUBLE) = 1 THEN p.rusher
          ELSE 'UNKNOWN'
        END AS ball_getter,
        p.play_type,
        CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END AS pass_plays,
        CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END AS rush_plays,
        p.epa,
        p.air_yards,
        p.yards_after_catch,
        p.yards_gained,
        p.first_down
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND p.play_type IN ('pass', 'run')
        AND (redzone IS NULL OR redzone = FALSE OR p.yardline_100 <= 20)
    ) s
    WHERE s.down = down
      AND s.distance_bucket_calc = distance_bucket
    GROUP BY offense_formation, personnel_bucket, ball_getter
    ORDER BY plays DESC, offense_formation, personnel_bucket
    LIMIT 100
  )
);
;

-- Function 2
CREATE OR REPLACE FUNCTION who_got_ball_by_offense_situation(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  offense_formation STRING COMMENT 'Offensive formation to filter by',
  personnel_bucket STRING COMMENT 'Parsed personnel bucket string (e.g., "5 OL, 1 RB, 1 TE, 3 WR, 1 QB")',
  down INT COMMENT 'Down to filter by (1-4)',
  distance_bucket STRING COMMENT 'Distance bucket to filter by: 1-2|3-6|7-10|>10'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: who got the ball (receiver on passes, rusher on runs) for a given formation, personnel, down and distance bucket'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'ball_getter', ball_getter,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      ball_getter,
      COUNT(*) AS plays,
      SUM(CAST(`pass` AS DOUBLE)) AS pass_plays,
      SUM(CAST(rush AS DOUBLE)) AS rush_plays,
      SUM(CAST(`pass` AS DOUBLE)) / COUNT(*) AS pass_rate,
      SUM(CAST(rush AS DOUBLE)) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.play_id,
        p.down,
        CASE
          WHEN p.ydstogo <= 2 THEN '1-2'
          WHEN p.ydstogo <= 6 THEN '3-6'
          WHEN p.ydstogo <= 10 THEN '7-10'
          ELSE '>10'
        END AS distance_bucket_calc,
        a.offense_formation,
        CONCAT(
          CAST(GREATEST(0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket_calc,
        CASE
          WHEN CAST(p.`pass` AS DOUBLE) = 1 THEN p.receiver
          WHEN CAST(p.rush AS DOUBLE) = 1 THEN p.rusher
          ELSE 'UNKNOWN'
        END AS ball_getter,
        p.posteam,
        p.season,
        p.`pass`,
        p.rush,
        p.epa,
        p.yards_gained,
        p.first_down,
        p.air_yards,
        p.yards_after_catch
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
    ) s
    WHERE s.offense_formation = offense_formation
      AND s.personnel_bucket_calc = personnel_bucket
      AND s.down = down
      AND s.distance_bucket_calc = distance_bucket
    GROUP BY ball_getter
    ORDER BY plays DESC
    LIMIT 100
  )
);
;

-- Function 3
CREATE OR REPLACE FUNCTION who_got_ball_by_down_distance(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  down INT COMMENT 'Down to filter by (1-4)',
  distance_bucket STRING COMMENT 'Distance bucket to filter by: 1-2|3-6|7-10|>10'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: for a down+distance bucket, list who got the ball (receiver on passes, rusher on runs)'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'ball_getter', ball_getter,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      ball_getter,
      COUNT(*) AS plays,
      SUM(CAST(`pass` AS DOUBLE)) AS pass_plays,
      SUM(CAST(rush AS DOUBLE)) AS rush_plays,
      SUM(CAST(`pass` AS DOUBLE)) / COUNT(*) AS pass_rate,
      SUM(CAST(rush AS DOUBLE)) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.play_id,
        p.down,
        CASE
          WHEN p.ydstogo <= 2 THEN '1-2'
          WHEN p.ydstogo <= 6 THEN '3-6'
          WHEN p.ydstogo <= 10 THEN '7-10'
          ELSE '>10'
        END AS distance_bucket_calc,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket,
        CASE
          WHEN CAST(p.`pass` AS DOUBLE) = 1 THEN p.receiver
          WHEN CAST(p.rush AS DOUBLE) = 1 THEN p.rusher
          ELSE 'UNKNOWN'
        END AS ball_getter,
        p.posteam,
        p.season,
        p.`pass`,
        p.rush,
        p.epa,
        p.yards_gained,
        p.first_down,
        p.air_yards,
        p.yards_after_catch
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
    ) s
    WHERE s.down = down
      AND s.distance_bucket_calc = distance_bucket
    GROUP BY ball_getter
    ORDER BY plays DESC
    LIMIT 100
  )
);
;

-- Function 4
CREATE OR REPLACE FUNCTION pbp_star()
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: sample of football_pbp_data (first 100 rows) for agent/cursor context'
RETURN (
  SELECT to_json(collect_list(struct(*)))
  FROM (
    SELECT *
    FROM football_pbp_data
    LIMIT 100
  )
);



CREATE OR REPLACE FUNCTION participation_star()
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: sample of football_participation (first 100 rows) for agent/cursor context'
RETURN (
  SELECT to_json(collect_list(struct(*)))
  FROM (
    SELECT *
    FROM football_participation
    LIMIT 100
  )
);
;

-- Function 5
CREATE OR REPLACE FUNCTION first_play_after_turnover(
  team STRING COMMENT 'Team abbrev used in pbp posteam (ex: SF, KC)',
  seasons ARRAY<INT> COMMENT 'Seasons to include (ex: array(2023,2024))'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive play tendencies for first play after turnover'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'play_type', play_type,
        'plays', plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards
      )
    )
  )
  FROM (
    -- your existing SELECT ... GROUP BY ...
    SELECT
      a.offense_formation,
      CONCAT(/* ... your personnel_bucket logic ... */) AS personnel_bucket,
      p.play_type,
      COUNT(*) AS plays,
      SUM(CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
      SUM(CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(CAST(success AS DOUBLE)) AS success_rate,
      AVG(yards_gained) AS avg_yards
    FROM football_pbp_data p
    LEFT JOIN football_participation a
      ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id) AND p.play_id = a.play_id
    WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
      AND p.posteam = team
      AND p.play_id = p.drive_play_id_started
      AND p.drive_end_transition IN ('INTERCEPTION', 'FUMBLE')
      AND a.offense_formation IS NOT NULL
      AND a.offense_personnel IS NOT NULL
      AND p.play_type IN ('pass', 'run')
    GROUP BY a.offense_formation, personnel_bucket, p.play_type
    ORDER BY plays DESC
    LIMIT 50
  )
);
;

-- Function 6
CREATE OR REPLACE FUNCTION tendencies_by_score_2nd_half(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive tendencies by score differential in 2nd half (Winning >10, Winning 1-9, Tied, Losing 1-9, Losing >10)'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'score_situation', score_situation,
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards
      )
    )
  )
  FROM (
    SELECT
      score_situation,
      offense_formation,
      personnel_bucket,
      COUNT(*) AS plays,
      SUM(CASE WHEN play_type = 'pass' THEN 1 ELSE 0 END) AS pass_plays,
      SUM(CASE WHEN play_type = 'run'  THEN 1 ELSE 0 END) AS rush_plays,
      SUM(CASE WHEN play_type = 'pass' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
      SUM(CASE WHEN play_type = 'run'  THEN 1 ELSE 0 END) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(CAST(success AS DOUBLE)) AS success_rate,
      AVG(yards_gained) AS avg_yards
    FROM (
      SELECT
        CASE
          WHEN p.score_differential > 10 THEN 'Winning >10'
          WHEN p.score_differential BETWEEN 1 AND 9 THEN 'Winning 1-9'
          WHEN p.score_differential = 0 THEN 'Tied'
          WHEN p.score_differential BETWEEN -9 AND -1 THEN 'Losing 1-9'
          WHEN p.score_differential < -10 THEN 'Losing >10'
        END AS score_situation,
        a.offense_formation AS offense_formation,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket,
        p.play_type,
        p.epa,
        p.success,
        p.yards_gained
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND p.game_half = 'Half2'
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND p.play_type IN ('pass', 'run')
    ) s
    GROUP BY score_situation, offense_formation, personnel_bucket
    ORDER BY score_situation, plays DESC
    LIMIT 100
  )
);
;

-- Function 7
CREATE OR REPLACE FUNCTION tendencies_by_drive_start(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive tendencies by drive start position (own <25, own 25-50, opponent territory)'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'drive_start_zone', drive_start_zone,
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards
      )
    )
  )
  FROM (
    SELECT
      drive_start_zone,
      offense_formation,
      personnel_bucket,
      COUNT(*) AS plays,
      SUM(CASE WHEN play_type = 'pass' THEN 1 ELSE 0 END) AS pass_plays,
      SUM(CASE WHEN play_type = 'run'  THEN 1 ELSE 0 END) AS rush_plays,
      SUM(CASE WHEN play_type = 'pass' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
      SUM(CASE WHEN play_type = 'run'  THEN 1 ELSE 0 END) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(CAST(success AS DOUBLE)) AS success_rate,
      AVG(yards_gained) AS avg_yards
    FROM (
      SELECT
        CASE
          WHEN p.yardline_100 > 75 THEN 'Own <25'
          WHEN p.yardline_100 BETWEEN 50 AND 75 THEN 'Own 25-50'
          WHEN p.yardline_100 < 50 THEN 'Opponent Territory'
        END AS drive_start_zone,
        a.offense_formation AS offense_formation,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket,
        p.play_type,
        p.epa,
        p.success,
        p.yards_gained
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND p.play_id = p.drive_play_id_started
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND p.play_type IN ('pass', 'run')
    ) s
    GROUP BY drive_start_zone, offense_formation, personnel_bucket
    ORDER BY drive_start_zone, plays DESC
    LIMIT 100
  )
);
;

-- Function 8
CREATE OR REPLACE FUNCTION tendencies_two_minute_drill(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  two_minute_drill BOOLEAN COMMENT 'If TRUE, restrict to plays with <2 minutes in 2nd or 4th quarter'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive formation tendencies during two-minute drill situations (under 2 minutes in 2nd or 4th quarter)'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch
      )
    )
  )
  FROM (
    SELECT
      a.offense_formation AS offense_formation,
      CONCAT(
        CAST(GREATEST(
          0,
          10 - (
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
          )
        ) AS STRING), ' OL, ',
        CAST(
          COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
          + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
        AS STRING), ' RB, ',
        CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
        CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
      ) AS personnel_bucket,
      COUNT(*) AS plays,
      SUM(CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END) AS pass_plays,
      SUM(CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END) AS rush_plays,
      SUM(CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
      SUM(CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END) / COUNT(*) AS rush_rate,
      AVG(p.epa) AS avg_epa,
      AVG(CAST(p.success AS DOUBLE)) AS success_rate,
      AVG(p.yards_gained) AS avg_yards,
      AVG(p.air_yards) AS avg_air_yards,
      AVG(p.yards_after_catch) AS avg_yards_after_catch
    FROM football_pbp_data p
    LEFT JOIN football_participation a
      ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
     AND p.play_id = a.play_id
    WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
      AND p.posteam = team
      AND a.offense_formation IS NOT NULL
      AND a.offense_personnel IS NOT NULL
      AND p.play_type IN ('pass', 'run')
      AND (
        two_minute_drill IS NULL
        OR two_minute_drill = FALSE
        OR (
          two_minute_drill = TRUE
          AND (
            (p.qtr = 2 AND p.quarter_seconds_remaining <= 120)
            OR (p.qtr = 4 AND p.quarter_seconds_remaining <= 120)
          )
        )
      )
    GROUP BY a.offense_formation, personnel_bucket
    ORDER BY plays DESC
    LIMIT 100
  )
);
;

-- Function 9
CREATE OR REPLACE FUNCTION who_got_ball_two_minute_drill(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for',
  offense_formation STRING COMMENT 'Offensive formation to filter by',
  personnel_bucket STRING COMMENT 'Parsed personnel bucket string (e.g., \"5 OL, 1 RB, 1 TE, 3 WR, 1 QB\")',
  two_minute_drill BOOLEAN COMMENT 'If TRUE, restrict to plays with <2 minutes in 2nd or 4th quarter'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: who got the ball during two-minute drill situations (receiver on passes, rusher on runs) for a given formation/personnel'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'ball_getter', ball_getter,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      ball_getter,
      COUNT(*) AS plays,
      SUM(CAST(`pass` AS DOUBLE)) AS pass_plays,
      SUM(CAST(rush AS DOUBLE)) AS rush_plays,
      SUM(CAST(`pass` AS DOUBLE)) / COUNT(*) AS pass_rate,
      SUM(CAST(rush AS DOUBLE)) / COUNT(*) AS rush_rate,
      AVG(epa) AS avg_epa,
      AVG(yards_gained) AS avg_yards,
      AVG(air_yards) AS avg_air_yards,
      AVG(yards_after_catch) AS avg_yards_after_catch,
      AVG(first_down) AS first_down_rate
    FROM (
      SELECT
        p.play_id,
        a.offense_formation,
        CONCAT(
          CAST(GREATEST(
            0,
            10 - (
              COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
              + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
            )
          ) AS STRING), ' OL, ',
          CAST(
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
          AS STRING), ' RB, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
          CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
        ) AS personnel_bucket_calc,
        CASE
          WHEN CAST(p.`pass` AS DOUBLE) = 1 THEN p.receiver
          WHEN CAST(p.rush AS DOUBLE) = 1 THEN p.rusher
          ELSE 'UNKNOWN'
        END AS ball_getter,
        p.posteam,
        p.season,
        p.`pass`,
        p.rush,
        p.epa,
        p.yards_gained,
        p.first_down,
        p.air_yards,
        p.yards_after_catch
      FROM football_pbp_data p
      LEFT JOIN football_participation a
        ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
       AND p.play_id = a.play_id
      WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
        AND p.posteam = team
        AND a.offense_formation IS NOT NULL
        AND a.offense_personnel IS NOT NULL
        AND (
          two_minute_drill IS NULL
          OR two_minute_drill = FALSE
          OR (
            two_minute_drill = TRUE
            AND (
              (p.qtr = 2 AND p.quarter_seconds_remaining <= 120)
              OR (p.qtr = 4 AND p.quarter_seconds_remaining <= 120)
            )
          )
        )
    ) s
    WHERE s.offense_formation = offense_formation
      AND s.personnel_bucket_calc = personnel_bucket
    GROUP BY ball_getter
    ORDER BY plays DESC
    LIMIT 100
  )
);
;

-- Function 10
CREATE OR REPLACE FUNCTION success_by_pass_rush_and_coverage(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: offensive success by number of pass rushers, man/zone type, and coverage type'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'number_of_pass_rushers', number_of_pass_rushers,
        'defense_man_zone_type', defense_man_zone_type,
        'defense_coverage_type', defense_coverage_type,
        'plays', plays,
        'pass_plays', pass_plays,
        'rush_plays', rush_plays,
        'pass_rate', pass_rate,
        'rush_rate', rush_rate,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards,
        'avg_air_yards', avg_air_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      a.number_of_pass_rushers AS number_of_pass_rushers,
      a.defense_man_zone_type AS defense_man_zone_type,
      a.defense_coverage_type AS defense_coverage_type,
      COUNT(*) AS plays,
      SUM(CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END) AS pass_plays,
      SUM(CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END) AS rush_plays,
      SUM(CASE WHEN p.play_type = 'pass' THEN 1 ELSE 0 END) / COUNT(*) AS pass_rate,
      SUM(CASE WHEN p.play_type = 'run'  THEN 1 ELSE 0 END) / COUNT(*) AS rush_rate,
      AVG(p.epa) AS avg_epa,
      AVG(CAST(p.success AS DOUBLE)) AS success_rate,
      AVG(p.yards_gained) AS avg_yards,
      AVG(p.air_yards) AS avg_air_yards,
      AVG(p.yards_after_catch) AS avg_yards_after_catch,
      AVG(p.first_down) AS first_down_rate
    FROM football_pbp_data p
    INNER JOIN football_participation a
      ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
     AND p.play_id = a.play_id
    WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
      AND p.posteam = team
      AND a.number_of_pass_rushers IS NOT NULL
      AND a.defense_man_zone_type IS NOT NULL
      AND a.defense_coverage_type IS NOT NULL
      AND p.play_type IN ('pass', 'run')
    GROUP BY a.number_of_pass_rushers, a.defense_man_zone_type, a.defense_coverage_type
    ORDER BY plays DESC
    LIMIT 100
  )
);
;

-- Function 11
CREATE OR REPLACE FUNCTION screen_play_tendencies(
  team STRING COMMENT 'The team to collect tendencies for',
  seasons ARRAY<INT> COMMENT 'The seasons to collect tendencies for'
)
RETURNS STRING
LANGUAGE SQL
COMMENT 'JSON rows: screen play tendencies (route=SCREEN) by down, distance, formation, personnel, and primary receiver'
RETURN (
  SELECT to_json(
    collect_list(
      named_struct(
        'down', down,
        'distance_bucket', distance_bucket,
        'offense_formation', offense_formation,
        'personnel_bucket', personnel_bucket,
        'primary_receiver', primary_receiver,
        'plays', plays,
        'avg_epa', avg_epa,
        'success_rate', success_rate,
        'avg_yards', avg_yards,
        'avg_yards_after_catch', avg_yards_after_catch,
        'first_down_rate', first_down_rate
      )
    )
  )
  FROM (
    SELECT
      p.down AS down,
      CASE
        WHEN p.ydstogo <= 2 THEN '1-2'
        WHEN p.ydstogo <= 6 THEN '3-6'
        WHEN p.ydstogo <= 10 THEN '7-10'
        ELSE '>10'
      END AS distance_bucket,
      a.offense_formation AS offense_formation,
      CONCAT(
        CAST(GREATEST(
          0,
          10 - (
            COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0)
            + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0)
          )
        ) AS STRING), ' OL, ',
        CAST(
          COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*RB', 1) AS INT), 0)
          + COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*FB', 1) AS INT), 0)
        AS STRING), ' RB, ',
        CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*TE', 1) AS INT), 0) AS STRING), ' TE, ',
        CAST(COALESCE(TRY_CAST(REGEXP_EXTRACT(a.offense_personnel, '(?i)(\\d+)\\s*WR', 1) AS INT), 0) AS STRING), ' WR, 1 QB'
      ) AS personnel_bucket,
      COALESCE(CAST(p.receiver AS STRING), 'UNKNOWN') AS primary_receiver,
      COUNT(*) AS plays,
      AVG(p.epa) AS avg_epa,
      AVG(CAST(p.success AS DOUBLE)) AS success_rate,
      AVG(p.yards_gained) AS avg_yards,
      AVG(p.yards_after_catch) AS avg_yards_after_catch,
      AVG(p.first_down) AS first_down_rate
    FROM football_pbp_data p
    INNER JOIN football_participation a
      ON p.game_id = COALESCE(a.nflverse_game_id, a.old_game_id)
     AND p.play_id = a.play_id
    WHERE array_contains(COALESCE(seasons, array(2023, 2024)), p.season)
      AND p.posteam = team
      AND a.route = 'SCREEN'
      AND a.offense_formation IS NOT NULL
      AND a.offense_personnel IS NOT NULL
      AND p.down IS NOT NULL
    GROUP BY
      p.down,
      distance_bucket,
      a.offense_formation,
      personnel_bucket,
      primary_receiver
    ORDER BY p.down, distance_bucket, plays DESC
    LIMIT 100
  )
);
;

