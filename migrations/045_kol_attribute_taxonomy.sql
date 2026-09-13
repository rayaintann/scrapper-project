-- 045_kol_attribute_taxonomy.sql
--
-- Dua tabel baru untuk Style & Personality sisi KOL, plus 40 baris master.
--
--     public.kol_attribute       master nilai   (40 baris)
--     public.kol_attribute_map   KOL <-> nilai  (kosong, diisi kurasi manual)
--
-- Aditif sepenuhnya. Tidak ada tabel yang diubah, tidak ada kolom yang
-- ditambahkan ke tabel existing, tidak ada DROP, dan tidak satu baris pun
-- dihapus atau diubah. Pola dan gaya mengikuti migration 036-044.
--
-- ============================================================================
-- KENAPA TABEL BARU, PADAHAL PRINSIPNYA REUSE DULU
-- ============================================================================
--
-- Dicek dulu. Sapuan `information_schema` atas 101 tabel:
--
--     column_name ILIKE '%style%'        -> 0 kolom
--     column_name ILIKE '%personality%'  -> 0 kolom
--     table_name  ILIKE '%style%'        -> 0 tabel
--     table_name  ILIKE '%personality%'  -> 0 tabel
--
-- Tidak ada rumah sama sekali. Tiga alternatif reuse ditolak:
--
--   l2_gold.kol_profile_card    di-regenerate asset Dagster tiap materialisasi,
--                               jadi data KURASI MANUAL akan tertimpa job. Dan
--                               tests/test_calculated_metrics.py sudah melarang
--                               kolom bernama `style` di sana.
--
--   kol_directory.category_ids  polanya cocok (uuid[] multi-nilai berkurasi),
--                               tapi array tidak bisa membawa `assigned_by` dan
--                               `assigned_at`. Untuk data yang ditempel orang,
--                               jejak itu bagian dari datanya.
--
--   agency_kol_accounts         sudah memegang atribut kurasi (`category_id`,
--                               `tier_id`), tapi grainnya per-agency. Style
--                               adalah sifat akun, bukan sifat hubungan agency
--                               dengan akun.
--
-- ============================================================================
-- KENAPA KUNCI UNIKNYA (kind, attribute_group, attribute_key)
-- ============================================================================
--
-- Label yang sama sah muncul di beberapa sumbu dengan arti berbeda:
--
--     Educational   Content Style . Communication Style . Creator Personality
--     Aesthetic     Content Style . Visual Style
--     Casual        Creator Personality . Visual Style
--
-- `Educational` sebagai Content Style berarti "bentuk kontennya mengajar";
-- sebagai Creator Personality berarti "kreatornya bertipe pengajar". Unik pada
-- label saja akan melebur keduanya.
--
-- ============================================================================
-- KENAPA MAP MENUNJUK kol_directory, DAN APA KONSEKUENSINYA
-- ============================================================================
--
-- `kol_directory` secara schema ACCOUNT/PLATFORM-level, bukan person-level:
-- PK per baris, `platform_id` sebagai kolom, dan 216 handle punya dua baris
-- (satu per platform). Menaruh atribut di sini TIDAK membuatnya person-level;
-- ia atribut per AKUN. Ditulis di sini supaya konsumen berikutnya tidak salah
-- anggap.
--
-- Kenapa tetap dipilih:
--   - cakupan terluas: 7.432 baris, vs social_account 7.208
--   - `category_ids` -- atribut multi-nilai berkurasi yang setara -- sudah di sini
--   - bukan per-agency
--
-- Kenapa BUKAN person entity: `l0_raw.kol_roster_import.influencer_id` sempat
-- jadi kandidat, tapi audit menolaknya. 20 influencer_id memuat 3+ akun dan
-- SELURUHNYA mencampur orang berbeda -- `8372` sendiri berisi 43 kreator tak
-- berhubungan. Ditambah 17 influencer_id berisi pecahan alamat (CSV column
-- shift), dan hanya ada 1 import batch sehingga stabilitas lintas-import belum
-- teruji. Tabel `person` TIDAK dibuat.
--
-- Jalur ke person-level tetap terbuka dan murah: karena map memakai FK
-- terpisah, menambah `person_id` nullable nanti tidak membongkar apa pun.
--
-- ============================================================================
-- ISI MASTER: 40 BARIS, GABUNGAN EXCEL + UI
-- ============================================================================
--
--     content_style        11
--     communication_style   9
--     creator_personality  13
--     visual_style          7
--
-- Digenerate dari `kol_attribute_taxonomy.TAXONOMY`, bukan diketik ulang.
-- tests/test_kol_attribute_taxonomy.py membandingkan file ini dengan modul
-- tersebut; kalau salah satu berubah sendiri, test gagal.
--
-- `source_origin` merekam asal tiap nilai. Tidak satu nilai pun dibuang meski
-- hanya ada di salah satu sumber:
--
--     hanya UI     Commentary, Demonstration, Expert, dan 4 nilai visual_style
--                  (Cinematic, Colorful, Lifestyle, Minimalist)
--     hanya Excel  Demo, Comedy, Demonstrative, Conversational, Data-driven,
--                  Visual-first, Testimonial, Creative, Tech-savvy, Reviewer,
--                  Premium, Luxury
--
-- Brand Personality (10) dan Brand Tone (8) SENGAJA tidak masuk: keduanya
-- atribut brand, bukan KOL. Rumahnya `public.brand`.
--
-- `Demonstration` (UI) vs `Demonstrative` (Excel, Communication Style) vs
-- `Demo` (Excel, Content Style) DIPERTAHANKAN terpisah. Menggabungkannya
-- keputusan bisnis yang belum diambil; aliasnya dicatat di
-- `kol_attribute_taxonomy.ALIAS_BELUM_DIPUTUSKAN`.

BEGIN;

-- ============================================================================
-- 1. MASTER
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.kol_attribute (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            varchar(20)  NOT NULL,
    attribute_group varchar(40)  NOT NULL,
    attribute_key   varchar(120) NOT NULL,
    label           varchar(80)  NOT NULL,
    source_origin   varchar(20)  NOT NULL,
    sort_order      integer      NOT NULL DEFAULT 0,
    is_active       boolean      NOT NULL DEFAULT true,
    created_at      timestamptz  NOT NULL DEFAULT now(),
    updated_at      timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT ck_kol_attribute_kind
        CHECK (kind IN ('style', 'personality')),
    CONSTRAINT ck_kol_attribute_group
        CHECK (attribute_group IN ('content_style', 'communication_style',
                                   'creator_personality', 'visual_style')),
    CONSTRAINT ck_kol_attribute_source
        CHECK (source_origin IN ('excel', 'ui', 'excel+ui')),
    CONSTRAINT uq_kol_attribute
        UNIQUE (kind, attribute_group, attribute_key)
);

COMMENT ON TABLE public.kol_attribute IS
    'Master Style & Personality sisi KOL. 40 baris, gabungan Excel '
    '(brand_style_personality.xlsx) dan UI prototype (AUTOME_2.html DNA2). '
    'Digenerate dari kol_attribute_taxonomy.TAXONOMY. Brand Personality dan '
    'Brand Tone TIDAK di sini -- keduanya atribut brand.';

COMMENT ON COLUMN public.kol_attribute.attribute_group IS
    'Sumbu sebenarnya. Label yang sama sah muncul di beberapa grup dengan '
    'arti berbeda, jadi grup ini bagian dari kunci unik.';

COMMENT ON COLUMN public.kol_attribute.source_origin IS
    'excel | ui | excel+ui -- asal nilai. Tidak satu nilai pun dibuang meski '
    'hanya ada di salah satu sumber.';

COMMENT ON COLUMN public.kol_attribute.is_active IS
    'Menonaktifkan nilai tanpa menghapusnya, supaya mapping lama tetap sah.';

-- ============================================================================
-- 2. MAPPING  KOL <-> ATTRIBUTE
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.kol_attribute_map (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kol_directory_id uuid        NOT NULL,
    kol_attribute_id uuid        NOT NULL,
    assigned_by      uuid,
    assigned_at      timestamptz NOT NULL DEFAULT now(),
    note             text,
    CONSTRAINT fk_kol_attribute_map_directory
        FOREIGN KEY (kol_directory_id) REFERENCES public.kol_directory(id),
    CONSTRAINT fk_kol_attribute_map_attribute
        FOREIGN KEY (kol_attribute_id) REFERENCES public.kol_attribute(id),
    CONSTRAINT uq_kol_attribute_map
        UNIQUE (kol_directory_id, kol_attribute_id)
);

COMMENT ON TABLE public.kol_attribute_map IS
    'Style & Personality yang ditempel ke satu AKUN KOL. Many-to-many: satu '
    'akun boleh banyak nilai, satu nilai boleh dipakai banyak akun.';

COMMENT ON COLUMN public.kol_attribute_map.kol_directory_id IS
    'PERHATIAN: kol_directory bergrain (platform, akun), BUKAN per orang. '
    'Atribut di sini atribut AKUN. Satu orang dengan Instagram dan TikTok '
    'punya dua baris kol_directory, jadi atributnya dikurasi dua kali. Tidak '
    'ada entity person di database ini.';

COMMENT ON COLUMN public.kol_attribute_map.assigned_by IS
    'Siapa yang menempelkan. Data ini kurasi manual, bukan hasil hitung, jadi '
    'jejaknya bagian dari datanya. FK ke public.user sengaja tidak dipasang '
    'karena tabel itu baru berisi 1 baris.';

-- Index untuk arah baca dominan: "atribut apa saja milik KOL ini".
-- Arah sebaliknya sudah dilayani uq_kol_attribute_map.
CREATE INDEX IF NOT EXISTS ix_kol_attribute_map_directory
    ON public.kol_attribute_map (kol_directory_id);

-- ============================================================================
-- 3. SEED MASTER  -- idempoten, tidak menimpa baris yang sudah ada
-- ============================================================================

INSERT INTO public.kol_attribute
    (kind, attribute_group, attribute_key, label, source_origin, sort_order)
VALUES
    ('style', 'content_style', 'content_style.educational', 'Educational', 'excel', 1),
    ('style', 'content_style', 'content_style.tutorial', 'Tutorial', 'excel+ui', 2),
    ('style', 'content_style', 'content_style.review', 'Review', 'excel+ui', 3),
    ('style', 'content_style', 'content_style.storytelling', 'Storytelling', 'excel+ui', 4),
    ('style', 'content_style', 'content_style.aesthetic', 'Aesthetic', 'excel', 5),
    ('style', 'content_style', 'content_style.entertaining', 'Entertaining', 'excel', 6),
    ('style', 'content_style', 'content_style.vlog', 'Vlog', 'excel+ui', 7),
    ('style', 'content_style', 'content_style.talking_head', 'Talking Head', 'excel+ui', 8),
    ('style', 'content_style', 'content_style.demo', 'Demo', 'excel', 9),
    ('style', 'content_style', 'content_style.comedy', 'Comedy', 'excel', 10),
    ('style', 'content_style', 'content_style.commentary', 'Commentary', 'ui', 11),
    ('style', 'communication_style', 'communication_style.educational', 'Educational', 'excel', 1),
    ('style', 'communication_style', 'communication_style.storytelling', 'Storytelling', 'excel', 2),
    ('style', 'communication_style', 'communication_style.demonstrative', 'Demonstrative', 'excel', 3),
    ('style', 'communication_style', 'communication_style.conversational', 'Conversational', 'excel', 4),
    ('style', 'communication_style', 'communication_style.data_driven', 'Data-driven', 'excel', 5),
    ('style', 'communication_style', 'communication_style.visual_first', 'Visual-first', 'excel', 6),
    ('style', 'communication_style', 'communication_style.humorous', 'Humorous', 'excel', 7),
    ('style', 'communication_style', 'communication_style.testimonial', 'Testimonial', 'excel', 8),
    ('style', 'communication_style', 'communication_style.demonstration', 'Demonstration', 'ui', 9),
    ('personality', 'creator_personality', 'creator_personality.professional', 'Professional', 'excel+ui', 1),
    ('personality', 'creator_personality', 'creator_personality.educational', 'Educational', 'excel+ui', 2),
    ('personality', 'creator_personality', 'creator_personality.relatable', 'Relatable', 'excel+ui', 3),
    ('personality', 'creator_personality', 'creator_personality.casual', 'Casual', 'excel+ui', 4),
    ('personality', 'creator_personality', 'creator_personality.entertaining', 'Entertaining', 'excel+ui', 5),
    ('personality', 'creator_personality', 'creator_personality.humorous', 'Humorous', 'excel+ui', 6),
    ('personality', 'creator_personality', 'creator_personality.inspirational', 'Inspirational', 'excel+ui', 7),
    ('personality', 'creator_personality', 'creator_personality.creative', 'Creative', 'excel', 8),
    ('personality', 'creator_personality', 'creator_personality.tech_savvy', 'Tech-savvy', 'excel', 9),
    ('personality', 'creator_personality', 'creator_personality.reviewer', 'Reviewer', 'excel', 10),
    ('personality', 'creator_personality', 'creator_personality.premium', 'Premium', 'excel', 11),
    ('personality', 'creator_personality', 'creator_personality.luxury', 'Luxury', 'excel', 12),
    ('personality', 'creator_personality', 'creator_personality.expert', 'Expert', 'ui', 13),
    ('style', 'visual_style', 'visual_style.aesthetic', 'Aesthetic', 'ui', 1),
    ('style', 'visual_style', 'visual_style.casual', 'Casual', 'ui', 2),
    ('style', 'visual_style', 'visual_style.professional', 'Professional', 'ui', 3),
    ('style', 'visual_style', 'visual_style.cinematic', 'Cinematic', 'ui', 4),
    ('style', 'visual_style', 'visual_style.colorful', 'Colorful', 'ui', 5),
    ('style', 'visual_style', 'visual_style.lifestyle', 'Lifestyle', 'ui', 6),
    ('style', 'visual_style', 'visual_style.minimalist', 'Minimalist', 'ui', 7)
ON CONFLICT (kind, attribute_group, attribute_key) DO NOTHING;

-- ============================================================================
-- 4. VERIFIKASI  -- gagal di sini membatalkan seluruh transaksi
-- ============================================================================

DO $verifikasi$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM public.kol_attribute;
    IF n <> 40 THEN
        RAISE EXCEPTION 'kol_attribute berisi % baris, seharusnya 40', n;
    END IF;

    SELECT count(*) INTO n FROM public.kol_attribute
     WHERE attribute_group = 'content_style';
    IF n <> 11 THEN RAISE EXCEPTION 'content_style % baris, seharusnya 11', n; END IF;

    SELECT count(*) INTO n FROM public.kol_attribute
     WHERE attribute_group = 'communication_style';
    IF n <> 9 THEN RAISE EXCEPTION 'communication_style % baris, seharusnya 9', n; END IF;

    SELECT count(*) INTO n FROM public.kol_attribute
     WHERE attribute_group = 'creator_personality';
    IF n <> 13 THEN RAISE EXCEPTION 'creator_personality % baris, seharusnya 13', n; END IF;

    SELECT count(*) INTO n FROM public.kol_attribute
     WHERE attribute_group = 'visual_style';
    IF n <> 7 THEN RAISE EXCEPTION 'visual_style % baris, seharusnya 7', n; END IF;

    -- Label yang sama HARUS boleh hidup di beberapa grup. Kalau `Educational`
    -- tinggal satu, kunci uniknya salah dan artinya melebur.
    SELECT count(*) INTO n FROM public.kol_attribute WHERE label = 'Educational';
    IF n <> 3 THEN
        RAISE EXCEPTION 'Label Educational muncul % kali, seharusnya 3', n;
    END IF;

    -- Tidak boleh ada nilai brand-side yang menyelinap masuk.
    SELECT count(*) INTO n FROM public.kol_attribute
     WHERE attribute_group IN ('brand_personality', 'brand_tone');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Ada % baris brand-side di master KOL', n;
    END IF;

    -- Mapping harus berdiri kosong: pengisiannya kurasi manual, bukan migrasi.
    SELECT count(*) INTO n FROM public.kol_attribute_map;
    IF n <> 0 THEN
        RAISE EXCEPTION 'kol_attribute_map sudah berisi % baris', n;
    END IF;

    -- Larangan lama tetap berlaku: tidak ada calculated metric di kartu L2.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('style', 'personality', 'content_style',
                           'creator_personality', 'cpe', 'cpv', 'emv');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Kolom terlarang muncul di kol_profile_card: % kolom', n;
    END IF;

    RAISE NOTICE 'OK: kol_attribute 40 baris (11/9/13/7), kol_attribute_map '
                 'berdiri kosong dengan FK + unique + index, kartu L2 utuh.';
END $verifikasi$;

COMMIT;
