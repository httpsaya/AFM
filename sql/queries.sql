-- 1
SELECT
    sender_id,
    receiver_id,
    COUNT(*) AS tx_count,
    ROUND(SUM(amount_kzt), 2) AS total_kzt
FROM transactions
GROUP BY
    sender_id,
    receiver_id
ORDER BY total_kzt DESC
LIMIT 10;

-- 2
WITH
    monthly AS (
        SELECT
            sender_id,
            STRFTIME ('%Y-%m', date) AS month,
            SUM(amount_kzt) AS monthly_total
        FROM transactions
        GROUP BY
            sender_id,
            month
    )
SELECT
    sender_id,
    month,
    ROUND(monthly_total, 2) AS monthly_total,
    ROUND(
        SUM(monthly_total) OVER (
            PARTITION BY
                sender_id
            ORDER BY month ROWS BETWEEN 2 PRECEDING
                AND CURRENT ROW
        ),
        2
    ) AS rolling_3m_sum
FROM monthly
ORDER BY sender_id, month;

-- 3
WITH
    pair AS (
        SELECT
            receiver_id,
            sender_id,
            SUM(amount_kzt) AS pair_total
        FROM transactions
        WHERE
            amount_kzt > 0
            AND receiver_valid = 1
            AND sender_valid = 1
        GROUP BY
            receiver_id,
            sender_id
    ),
    total AS (
        SELECT receiver_id, SUM(amount_kzt) AS grand_total
        FROM transactions
        WHERE
            amount_kzt > 0
            AND receiver_valid = 1
        GROUP BY
            receiver_id
    )
SELECT
    p.receiver_id,
    p.sender_id AS dominant_sender,
    ROUND(
        p.pair_total * 100.0 / t.grand_total,
        1
    ) AS share_pct
FROM pair p
    JOIN total t ON p.receiver_id = t.receiver_id
WHERE
    p.pair_total * 1.0 / t.grand_total > 0.7
    AND t.grand_total > 1000000
ORDER BY share_pct DESC;