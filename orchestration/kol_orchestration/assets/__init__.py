"""Asset Dagster untuk pipeline KOL, dikelompokkan per layer.

    harmonization.py      l0_harmonization.{ig,tt}_{profile,post}   -- Fase 1b
    silver.py             l1_silver.unified_{profile,post}          -- Fase 1b
    feature_engagement.py feature.{ig,tt}_engagement_analysis       -- Fase 1a
    feature_post.py       feature.{ig,tt}_post_analysis             -- Fase 1c
    gold.py               l2_gold.kol_metric_daily                  -- SCRUM-513
                          l2_gold.kol_metric_monthly                -- SCRUM-516
    gold_profile.py       l2_gold.kol_profile_card                  -- SCRUM-514

`gold.py` berisi asset yang digerakkan POST (metric_date dari posted_at);
`gold_profile.py` yang digerakkan PROFIL (grain per akun, tanpa tanggal).
Pemisahannya sengaja -- perbedaan grain itu yang jadi alasan kedua tabel ada.
"""
