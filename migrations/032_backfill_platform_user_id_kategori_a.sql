-- =====================================================================
-- 032_backfill_platform_user_id_kategori_a.sql
-- Mengisi identity anchor public.kol_directory.platform_user_id untuk
-- 101 akun KATEGORI A yang sudah di-review dan di-approve.
--
-- KENAPA HANYA 101, BUKAN 892
--   Kriteria "tier directory = tier L1" saja meloloskan 892 akun, tapi itu
--   bukti lemah: rentang Mid-Tier (50rb-500rb) lebar 10x, jadi akun bisa
--   berubah 400% tanpa pindah tier.
--
--   Kategori A menambahkan syarat penguat, dan hanya 101 yang memenuhi:
--     * verified oleh actor (akun bercentang sulit direbut orang lain), ATAU
--     * >= 2 snapshot dengan platform_user_id yang SAMA (identitas
--       terkuatkan oleh pengulangan)
--
--   Rincian: 91 verified saja, 9 verified + >=2 snapshot, 1 >=2 snapshot saja.
--   Semuanya TikTok. 0 akun punya platform_user_id yang berubah antar snapshot.
--
--   Mengancor identity yang SALAH bersifat permanen dan justru mengunci
--   kesalahan, jadi 791 akun kategori B sengaja dibiarkan unanchored sampai
--   ada bukti tambahan.
--
-- YANG TIDAK DILAKUKAN
--   * Tidak menghitung ulang kandidat -- daftar di bawah adalah hasil
--     query 2026-09-07 yang sudah di-review, ditulis literal.
--   * Tidak menyentuh followers_count, scrape_status, atau kolom lain.
--   * Tidak menimpa anchor yang sudah ada (WHERE platform_user_id IS NULL).
--   * Tidak menghapus apa pun.
--
-- URUTAN
--   Jalankan SEBELUM migration 030. Gerbang identity tanpa anchor tidak
--   melindungi apa pun.
--
-- IDEMPOTEN
--   Dijalankan kedua kali akan mengenai 0 baris (semua sudah terisi), dan
--   guard di bawah akan menggagalkannya dengan pesan yang jelas. Itu
--   disengaja: kalau angkanya bukan 101, ada yang tidak sesuai harapan dan
--   transaksi harus mundur, bukan diteruskan.
--
-- ROLLBACK
--   UPDATE public.kol_directory SET platform_user_id = NULL
--    WHERE id IN (<101 kol_id di daftar VALUES di bawah>);
-- =====================================================================

BEGIN;

DO $backfill$
DECLARE
  n_terpengaruh int;
BEGIN
  WITH anchor(kol_id, puid) AS (
    VALUES
    ('5f336f2d-8ae2-4002-b456-1c956a274b15'::uuid, '6740954038932227074'),  -- ibnuwardani
    ('3f8232fc-ac7f-447f-b0ec-5cee130ee3c6'::uuid, '6780704573159572481'),  -- iben_ma
    ('9af7e5b8-8967-46ea-9ace-7f84b7e879ca'::uuid, '6545364556201787393'),  -- saalhaerid
    ('5ab1c10c-e701-4631-a37a-7e4272956e4c'::uuid, '6701928715321967618'),  -- jharnabhagwani
    ('6b54df83-8c12-4176-95c3-857de80da254'::uuid, '6807721790129046529'),  -- sptrakori_
    ('4815a3e8-234e-4a76-8112-4e7b01c5f1fa'::uuid, '6784819322114327553'),  -- lalitahutami
    ('934b0de4-d57a-4798-a36f-79dc15bc07b0'::uuid, '6790387175797588993'),  -- ditanganu
    ('8e0cdd34-85b3-446c-ad96-d1d19a9d32db'::uuid, '6787733906965709826'),  -- hesfinatia
    ('6115ab2f-8e56-4656-989d-a0a2895e8b43'::uuid, '6779211370271720450'),  -- erickapineda09
    ('b5c58aa0-c1ee-40a4-9ba0-11befb331bd6'::uuid, '6861839750992266241'),  -- pojoksatu.id
    ('febb54fe-4950-47fa-aa60-8521ef677caa'::uuid, '6788643430459098113'),  -- eunicetjoaa
    ('ce00cfff-7785-4582-b956-7b1885305396'::uuid, '6649559536254910465'),  -- nanakoot
    ('3e91a4aa-5f47-4cc6-b0a2-7b903b47f263'::uuid, '7050929531251065857'),  -- pandawaragroup
    ('68fdc2e2-e5e7-4745-8f67-052ed1d0a630'::uuid, '6832646631553696769'),  -- dennysumargoreal
    ('7cf3b6a5-a45c-48b3-be7b-8189fca46233'::uuid, '6776121811417138178'),  -- yourrkayesss
    ('a944dfa2-38b1-4962-814a-997fc9c651c7'::uuid, '6924102554779468802'),  -- efritaasmr
    ('7141a6c4-86f0-4b0e-b6af-3509f0f820db'::uuid, '6874394682941490178'),  -- mursid241
    ('aa4e4ec2-cb29-457a-aca9-73e668b220d3'::uuid, '6781492212108985346'),  -- dimsthemeatguy
    ('f2e8a875-e9c3-4db8-a441-0fe043763440'::uuid, '6767543999118787585'),  -- arafahrianti02
    ('0f23dced-231f-4380-8b98-2349b05cab12'::uuid, '262216949357801472'),  -- imeyhou
    ('94dfc30e-a022-4fea-b747-0bb8ba410a0c'::uuid, '6772201774717748225'),  -- celinenobleza
    ('749fa2b4-ebd0-44bd-9662-52c2da2c6686'::uuid, '6621549396097089538'),  -- megandomanii
    ('dc84f274-8bed-44db-baf4-e7b6845f8309'::uuid, '6557578464596541442'),  -- syahnazsadiqah
    ('61d3eaba-4d4b-464d-a574-d33f08e91b63'::uuid, '6782055341820855298'),  -- cheekykiddo
    ('1b3afc5a-ff2c-4723-bb2e-d33bb9989c91'::uuid, '6925679643459322882'),  -- bangsaonline
    ('77b96ce0-f4eb-45ec-af1d-42877b54588a'::uuid, '6804731766209807361'),  -- drrichardlee
    ('16b3e380-ef85-45e5-8258-fd817fccb7ef'::uuid, '6769117225413723138'),  -- milaalawiyah
    ('9988e83b-3588-4b04-a7b2-f1551a89e813'::uuid, '6784740637666345986'),  -- alfyfatmasaga
    ('cb77592d-72f1-49e8-84f9-6fc630991385'::uuid, '6730959951941354498'),  -- __ehan
    ('6e0ae62f-7d62-419f-a000-75f741bd0586'::uuid, '139380100038426624'),  -- auranixie
    ('770ac4dc-c385-45a3-aa96-fbf86d5c5ec2'::uuid, '6800357762883830785'),  -- baldtwins
    ('de8a4c94-f595-4f8e-9e20-2a671a82eac7'::uuid, '6748085164792579073'),  -- jennifer.coppen
    ('bcaf8fa4-a14e-4f7b-b0ff-b7d4e275b279'::uuid, '6770263146202596353'),  -- tasyafarasya
    ('236262b5-364f-4188-a0cf-2be0d2a62b03'::uuid, '6749609050776142850'),  -- catherineealicia
    ('a22c44e6-1920-4b6b-95f4-658e0e565a12'::uuid, '6526793073236934658'),  -- zaraanih
    ('57ceea27-1e4e-43f3-a5f7-cf892ac059d3'::uuid, '6655029316105338881'),  -- agnes_jennifer
    ('18fe8528-d113-4143-b831-831b31656794'::uuid, '6866301121347060738'),  -- leyladerina
    ('30e412bd-4e94-42af-8a0c-249c2d6efa8f'::uuid, '6535283582808834049'),  -- riyukabunga
    ('1e5da034-7b86-4967-8482-3d68167be6e7'::uuid, '6780233428689372162'),  -- sahilmulachela
    ('1cfa6644-35e8-4e90-a947-85f71a444a40'::uuid, '6872015774254531585'),  -- soimah_pancawati
    ('51c44ddd-2867-4979-85e8-20a7b0441514'::uuid, '6785480733369828353'),  -- mmivia
    ('d7112085-c197-42ab-98c2-5623dad51d53'::uuid, '72332155659'),  -- ayuwisya666
    ('5bf4f86b-32c5-49f9-9df4-31cc39fea40c'::uuid, '6764317454060733441'),  -- ejpeace.ent
    ('914270ae-2d85-4603-acf6-64ad76d1abf6'::uuid, '6865772894833607682'),  -- daenkrukka
    ('0cb3641a-e415-47fc-8c88-7acf6dd2ddeb'::uuid, '6746913646390395906'),  -- panggilakubambang
    ('5248b147-ae24-4912-b408-d3b2cac9c2bf'::uuid, '6740176748304139265'),  -- putrizianii
    ('22e7b7ed-cb0b-4a33-9f72-9714a34bcef9'::uuid, '6774690390625797122'),  -- laurasiburian
    ('f88cbc9d-1ec1-49ee-a129-a69ad766b3c0'::uuid, '6794373343464702978'),  -- aldogiustino21
    ('b282fd3e-23e4-462f-8144-e209d4d8621e'::uuid, '6782111281510302722'),  -- geyghea
    ('0612f0af-ff44-4303-8492-b435da9185dc'::uuid, '6786513857324467202'),  -- janes_cs
    ('43fdf924-e15a-408b-8e22-ebfe6333f35f'::uuid, '6565434543783591938'),  -- maspaijooo
    ('c41a05f8-5fde-4ce0-9968-28695688cb49'::uuid, '6922780637569909761'),  -- risyadandson
    ('76a1b22b-d02b-4162-88d3-87c5c8d0110e'::uuid, '6739102131528008705'),  -- florie_aa_
    ('3c73cac0-4df6-4405-9557-a86bd8776ee1'::uuid, '20443463'),  -- marshaaruan
    ('95edbf6a-e1c8-4661-9713-648d433d362a'::uuid, '6629989520567877638'),  -- angggiiie
    ('32d911cb-13c1-4296-9234-8232c34174ab'::uuid, '6517838769620521999'),  -- karenkurniawan_kk
    ('2eeb471f-7b53-4652-a8d6-2d0eb0d6a4f5'::uuid, '6737136236877644801'),  -- karmalogy
    ('3df22345-fda4-4da4-a826-277fabf965b2'::uuid, '6952358308192551938'),  -- skupakping
    ('803a7025-e139-40f6-bdbb-09c52edf4177'::uuid, '6806148524745901058'),  -- dillaprb
    ('40dfff81-891a-4eff-8a39-d760eedc8ec3'::uuid, '6780898147533227013'),  -- mumukdaneno
    ('e901fcb1-5bee-48fa-926c-80086d63dbbe'::uuid, '6562347006001070085'),  -- sunnydahye_
    ('05c2b39d-2e87-49a5-8622-b8b117d487bd'::uuid, '6776992777324659714'),  -- aymanalts
    ('07b330c3-4191-4351-9cf6-e81ee820d8f0'::uuid, '289465396443877376'),  -- dhiarcom
    ('5205c471-3d7c-4daf-b4c5-c425f4eba65b'::uuid, '6699719203564667906'),  -- gabriellaekaputrii
    ('fffd1ef6-c9a9-449b-9748-fcd6f5c4c198'::uuid, '6657676054309650434'),  -- itsyourchel
    ('d4a4b5f6-37c5-4e37-8b99-59fd4eb8edf3'::uuid, '6781685270724658177'),  -- nabilasyabanaa
    ('4a6846bf-e277-4d7b-acd7-a53f156a5283'::uuid, '6781189378610938881'),  -- raymondchins
    ('d3b2ccc0-773a-4f0d-97be-2c48a4d5c26b'::uuid, '6582562416017227778'),  -- clarestatok
    ('a3aa236e-537b-40b7-abea-4b9b8bd59921'::uuid, '6724692579398714370'),  -- farrajaidi
    ('755f15a1-58cf-445c-bf94-d19f30357a15'::uuid, '6762866599643350017'),  -- shella_fernanda29
    ('e6a36ec5-95e0-49f6-b9da-1647424f6b93'::uuid, '6625992912302063618'),  -- dinararizqiyyaraf93
    ('73d61b7a-ee10-476d-8d30-2583f88c89fe'::uuid, '6641668345618333697'),  -- bukanwulanwu
    ('a5cbea7f-39ae-4ed2-b9eb-169312e0d5ff'::uuid, '6800262875941848066'),  -- felicia.tjiasaka
    ('8dea9473-9714-4db8-80da-44e610ed90c8'::uuid, '6589424878259126273'),  -- willyanggawinata
    ('9e97f7d3-de60-4802-9561-1542804cf4ce'::uuid, '6767457997838025730'),  -- farhanbashel
    ('29ab35fe-7f75-4c3d-b974-319b64d4e276'::uuid, '6789201226162439170'),  -- papiabeabeabe
    ('90d76d04-dc29-401d-a846-b796bea28ae8'::uuid, '6508329815865868290'),  -- vansa.be
    ('8daece0c-6158-4099-8ac6-d067fbc58e8e'::uuid, '6573914838866395138'),  -- adenalfurqon
    ('94bac0aa-245c-4c34-86b2-11bba8852f35'::uuid, '6834970962334041089'),  -- anisabasyir
    ('283928a8-162a-410f-a557-f3f50a647fc5'::uuid, '6878881461910144001'),  -- beritainspira_
    ('e3899556-0bd6-4141-a7aa-0ab105f1ae28'::uuid, '6709972962671723521'),  -- nopeknovian
    ('5adea4b0-cb72-44b9-8fdc-e1baf8cc5984'::uuid, '6790162719373149185'),  -- dr.mariojohan
    ('d61a0a5a-499e-4cbd-aa8b-66f4bcdd2bae'::uuid, '6527483100989456385'),  -- faizsadad
    ('96a45732-cad3-4143-9b37-eca57998e680'::uuid, '12729988'),  -- farizaynn
    ('71bbce35-5095-46b2-b1c0-4e6bc154c59f'::uuid, '6762820010327999489'),  -- kezializina
    ('04ea9155-48f3-4401-bfb4-6c4d35d67403'::uuid, '6742019373689930758'),  -- maharajasp8
    ('559b3751-f8e7-4c3a-a880-4ad1d83c086f'::uuid, '71516433640'),  -- salyangkamu
    ('d23661c9-399a-475d-9743-80ae3e781e47'::uuid, '26765992'),  -- haloakuclay
    ('df560a94-5c09-477c-b259-8c86a0a0490d'::uuid, '7011116374643835931'),  -- sport77official
    ('2f1626de-c2ef-4c32-a3b8-2906f8992551'::uuid, '6767220149638628354'),  -- josephinetheaa
    ('66955777-84f8-4146-9d69-a5d2a4f14031'::uuid, '7371835092715684907'),  -- instagram
    ('24fea5ec-41c4-4e7a-bdaf-2c6dab6017e8'::uuid, '6780337728322028545'),  -- andreaslukita_
    ('544db3b8-140e-4b01-b869-dc6fcc571ce2'::uuid, '6579768453279973377'),  -- tasyakamilaofficial
    ('ccdca9cc-0bd6-401a-8173-5b4259751407'::uuid, '53322089369190400'),  -- monicasahr
    ('3b6b2b64-58d8-4b26-a0e0-60b5c04799e4'::uuid, '6947770434206548997'),  -- dairyqueen
    ('2c21adf3-0f09-4c3a-a48b-595db7781c30'::uuid, '26681805'),  -- annabellesjy
    ('905672ab-1b82-4e50-8d72-5f84eb1e98c5'::uuid, '6740107383982408705'),  -- bailafauri
    ('db67c86c-d45b-497e-9eea-8767e57f367a'::uuid, '7010811599787820038'),  -- twitter
    ('cd9ce17c-74bf-4b99-a8e3-f82576a20fad'::uuid, '6782323190267134978'),  -- femaledailynetwork
    ('6cb311b8-daed-40c6-9101-bccb03bab9ad'::uuid, '6828932313495421953'),  -- kei.savourie
    ('3e8ff058-c55b-4f8c-9245-20cacca7ffb6'::uuid, '6772394439648494593')  -- wulanestriyani
  )
  UPDATE public.kol_directory d
     SET platform_user_id = a.puid,
         updated_at       = now()
    FROM anchor a
   WHERE d.id = a.kol_id
     AND d.platform_user_id IS NULL;   -- hanya mengisi, tidak pernah menimpa

  GET DIAGNOSTICS n_terpengaruh = ROW_COUNT;

  IF n_terpengaruh <> 101 THEN
    RAISE EXCEPTION
      'Backfill anchor mengenai % baris, seharusnya tepat 101. Transaksi dibatalkan.',
      n_terpengaruh;
  END IF;

  RAISE NOTICE 'OK: 101 identity anchor terisi.';
END $backfill$;

-- ---------------------------------------------------------------------
-- Verifikasi pasca-backfill
-- ---------------------------------------------------------------------
DO $verifikasi$
DECLARE
  n_tiktok int;
  n_salah  int;
BEGIN
  SELECT count(*) INTO n_tiktok
  FROM public.kol_directory d
  JOIN public.platforms p ON p.id = d.platform_id
  WHERE p.key = 'tiktok' AND d.platform_user_id IS NOT NULL;

  IF n_tiktok <> 101 THEN
    RAISE EXCEPTION 'KOL TikTok ber-anchor = %, seharusnya 101', n_tiktok;
  END IF;

  -- anchor harus sama dengan platform_user_id snapshot L1 terbaru
  SELECT count(*) INTO n_salah
  FROM public.kol_directory d
  JOIN public.kol_social_account ksa ON ksa.kol_id = d.id
  JOIN (SELECT DISTINCT ON (social_account_id) social_account_id, platform_user_id
          FROM l1_silver.unified_profile
         WHERE platform_user_id IS NOT NULL
         ORDER BY social_account_id, date DESC) u
    ON u.social_account_id = ksa.social_account_id
  WHERE d.platform_user_id IS NOT NULL
    AND d.platform_user_id <> u.platform_user_id;

  IF n_salah <> 0 THEN
    RAISE EXCEPTION 'Ada % anchor yang tidak cocok dengan L1', n_salah;
  END IF;

  RAISE NOTICE 'OK: 101 anchor TikTok terpasang dan cocok dengan L1.';
END $verifikasi$;

COMMIT;
