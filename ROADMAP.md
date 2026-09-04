# VOLTRAN Yol Haritası

Son güncelleme: 4 Eylül 2026
Mevcut sürüm: \`0.1.0\`

Bu belge hedef listesinden çok bir uygulama planıdır. Bir madde ancak kodu, otomatik testi,
hata davranışı ve kullanıcı dokümantasyonu birlikte hazırsa tamamlanmış sayılır.

## Durum tanımları

- **Tamamlandı:** Kullanıcı yüzeyi ve otomatik testleri mevcut.
- **Kısmi:** Çalışan temel var, ancak ilgili gereksinimin tamamı karşılanmıyor.
- **Planlandı:** Uygulama henüz yok.
- **Ertelendi:** Yakın dönem sürüm hedefi değil.

## Mevcut durum

Bu tablo mevcut `main` dalının doğrulanmış durumudur. Ayrıntılı gereksinim matrisi tablonun
altındadır; aşağıdaki "eksik" sütunu yeni iş seçiminde esas alınır.

| Alan | Durum | Mevcut | Eksik |
| --- | --- | --- | --- |
| CLI ve paketleme | Kısmi | `doctor`, `run`, `history`, `replay`, `cancel`, `bench`, `dashboard`, `unlock`, `config`; uv paketi ve macOS betiği | Kurulumun kullanıcı onayıyla uygulanması ve tekrarlanabilir release süreci |
| Sağlayıcı adaptörleri | Kısmi | Codex, Claude ve Antigravity; timeout ve süreç temizliği | Sürüm uyumluluk matrisi ve gerçek CLI smoke testleri |
| Quick/expert | Kısmi | Router seçimi, timeout, normalize sonuç, hata raporu, `--provider` izin listesi, kullanıcı iptali (`voltran cancel`, FR-15) | Paralel alt görev yürütme |
| Council | Kısmi | hcom oturumu, farklı sağlayıcılar, iki tur ve bağlam bütçesi, açık uzlaşma/itiraz kaydı, izin listesine uyum | Ajanların birbirinin katkısını gerçekten gördüğünün ve yanıtladığının olay zincirinden doğrulanması; kısmi durum sözlüğü |
| Router | Kısmi | Yetenek, erişilebilirlik, moda göre puanlama ve doğrulanan sağlayıcı izin listesi | Kota, maliyet, gecikme ve oturum sağlığı |
| Gizlilik | Tamamlandı | Secret/PII maskeleme (giden ve kayıt yolu), hassasiyet sınıflandırması, hassas görevde otomatik council genişlemesinin engellenmesi, sağlayıcı izin listesi, dry-run veri paylaşım önizlemesi ve bağlam bütçesi/bölüm seçimi | SEC-01..SEC-05 karşılandı; kalan gizlilik işi yok |
| Yazma güvenliği | Kısmi | Atomik dosya kilidi, council'da tek yazıcı, detached Git worktree, binary inceleme patch'i; ana checkout'a otomatik uygulama yok | Üçüncü taraf CLI'lar için worktree dışına erişimi OS düzeyinde engelleyen ortak sandbox yok |
| Raporlama | Kısmi | Markdown/JSON, rol, sağlayıcı, durum ve council güven alanları | Kanıtlar ve isteğe bağlı ham uzman çıktıları |
| Geçmiş | Tamamlandı | Maskelenmiş SQLite özeti, son çalışmalar ve `voltran replay <run_id>` (FR-12) | - |
| Benchmark | Kısmi | Üç sabit senaryo; durum, süre ve uzlaşma kaydı | Altın cevaplar, kalite değerlendirmesi ve karşılaştırmalı ölçüm |
| Test ve CI | Kısmi | Python 3.11–3.14, macOS/Linux, 182 test, %89.11 kapsam (`hcom_client` %94, `providers/cli` %96), CI eşiği %83 | Toplam %90 ve gerçek CLI smoke testleri |
| Dashboard | Kısmi | Ajan, olay, kilit ve geçmiş görünümü | Hata dayanıklılığı ve uzun süreli kullanım testi |

## Gereksinim matrisi

| Gereksinim | Durum | Kanıtlanan kapsam | Kalan net iş |
| --- | --- | --- | --- |
| UR-01 Tek görev girişi | Tamamlandı | `voltran run` tek istemden plan ve rapor üretir | - |
| UR-02 Önerilen mod | Tamamlandı | Komutan otomatik mod seçer; `--explain` gerekçeyi gösterir | - |
| UR-03 Elle geçersiz kılma | Kısmi | Mod ve sağlayıcı izin listesi değiştirilebilir | Rol dağılımı için kullanıcı yüzeyi yok |
| UR-04 Kurulum yardımı | Kısmi | `doctor` eksikleri ve önerileri raporlar | Kurulum komutunu kullanıcı onayıyla uygulayan akış yok |
| UR-05 Tek sonuç | Kısmi | Tek nihai özet üretilir | İsteğe bağlı ham uzman çıktısı görünümü yok |
| UR-06 Şeffaflık | Kısmi | Sağlayıcı, rol, durum, anlaşmazlık ve güven alanları var | Uzman kanıt/risk/artifact alanları Markdown'da görünmüyor |
| UR-07 Türkçe önceliği | Kısmi | CLI ve varsayılan rapor Türkçe | Görev diline otomatik geçiş yok |
| FR-01 Sistem teşhisi | Kısmi | Platform, mimari, Python, CLI, sürüm, dizin ve bağımlılık kontrolleri var | Güvenilir oturum durumu ve gerçek sürüm uyumluluğu yok |
| FR-02 Sağlayıcı adaptörleri | Tamamlandı | Üç adaptör ortak arayüzü uygular | - |
| FR-03 Yetenek keşfi | Kısmi | Temel yetenekler Router puanlamasına girer | Bağlam sınırı ve gerçek oturum sağlığı yetenek sözleşmesinde yok |
| FR-04 Görev sınıflandırma | Kısmi | Basit görev türü/karmaşıklık ve hassasiyet sezgileri var | Araç, süre/kota etkisi ve paralelleştirilebilirlik modeli eksik |
| FR-05 Plan üretimi | Kısmi | Doğrulanan `TaskPlan` ve alt görev kimliği/rolü/amacı var | Bağımlılık, alt görev bazlı izin/timeout ve beklenen şema eksik |
| FR-06 Yönlendirme | Kısmi | Yetenek, izin, uygunluk ve erişilebilirlik kullanılır | Kota/maliyet, gecikme ve oturum sağlığı politikası eksik |
| FR-07 Paralel yürütme | Planlandı | - | Bağımsız alt görev üretimi ve eşzamanlı, hata yalıtımlı yürütme |
| FR-08 Kontrollü iletişim | Kısmi | İki tur, süre ve bağlam sınırı uygulanır | Ajanlar arası gerçek yanıt ilişkisi doğrulanmıyor |
| FR-09 Ortak sentez | Kısmi | Açık konsensüs ve çözülemeyen itirazlar korunur | Tek taraflı marker yerine katılımcı/yanıt zinciri şartı |
| FR-10 Çıktı sözleşmesi | Tamamlandı | Yapılandırılmış alanlar ayrıştırılır; bilinen status eşanlamlıları kanonikleşir | - |
| FR-11 Son rapor | Kısmi | Sonuç, dağılım, anlaşmazlık, güven ve sonraki adım var | Kanıt, belirsizlik, risk, artifact ve ham çıktı bölümleri eksik |
| FR-12 Geçmiş/replay | Tamamlandı | Plan/politika saklama, göç ve maskeli yeniden oynatma var | - |
| FR-13 Yapılandırma | Tamamlandı | CLI > proje > kullanıcı > varsayılan ve köken gösterimi var | - |
| FR-14 Kuru çalışma | Tamamlandı | Çağrı/sağlayıcı/veri paylaşımı model çağrısı olmadan gösterilir | - |
| FR-15 İptal/zaman aşımı | Tamamlandı | Timeout, Ctrl+C, `cancel`, PID kimliği ve süreç temizliği var | - |
| SEC-01 Gizli değer koruması | Tamamlandı | Giden veri, hata ve kalıcı kayıt yollarında maskeleme var | - |
| SEC-02 Sağlayıcı izin listesi | Tamamlandı | `--provider` Router ve council'a uygulanır | - |
| SEC-03 Hassas veri sınıflandırması | Tamamlandı | Beş sınıf uyarılır; otomatik council genişlemesi engellenir | - |
| SEC-04 Veri minimizasyonu | Tamamlandı | Karakter bütçesi ve satır aralığı uygulanır | - |
| SEC-05 Yerel maskeleme | Tamamlandı | Kimlik, finans, iletişim ve secret desenleri yerelde maskelenir | - |
| SEC-06 Komut güvenliği | Tamamlandı | Model metni kabuk olarak çalıştırılmaz; yazma açık `--write` ister | - |
| SEC-07 Dosya sınırları | Kısmi | Yazma detached worktree'de; patch incelemesiz uygulanmaz | Üç sağlayıcı için worktree dışı okuma/yazmayı ortak bir OS sandbox ile engelle |

Özet: **14 tamamlandı, 14 kısmi, 1 planlandı.** Worktree izolasyon paketi tamamlandı;
ancak SEC-07'nin mutlak dosya erişim sınırı henüz tamamlanmış sayılmıyor. Güvenlik regresyonu
yaratmadan sıradaki iş SEC-07 sandbox katmanı; ardından FR-11, FR-08/FR-09 ve FR-07'dir.

## Sıradaki paket: güvenilir 0.1.x

Bu paket bitmeden yeni büyük özellik veya masaüstü arayüzü öncelik değildir.

### P0 — Sağlayıcı izin politikası (SEC-02, UR-03) — **Tamamlandı**

- [x] \`voltran run --provider\` tek, çoklu ve virgülle ayrılmış izin listesi kabul eder.
- [x] Politika Router üzerinden taşınır; bilinmeyen anahtar sessizce yok sayılmaz, hata verir.
- [x] Council için iki farklı erişilebilir sağlayıcı yoksa açık hata üretilir.
- [x] Dry-run çıktısı hangi verinin hangi sağlayıcıya gideceğini ve çağrı sayısını gösterir.

Kabul ölçütü: karşılandı. İzin verilmeyen sağlayıcı plana hiç girmediği için hcom
rollerinde de görünemez; tek, çoklu, geçersiz, erişilemeyen ve kuru çalışma senaryoları
`tests/test_router.py` ve `tests/test_cli.py` içinde testlidir.

### P0 — Hassas veri sınıflandırması (SEC-03) — **Tamamlandı**

- [x] \`classifier.py\` finans, sağlık, kimlik, iletişim ve kimlik bilgisi sınıflarını üretir;
      yapısal desenler (TCKN, IBAN, kart, e-posta, telefon, anahtar/parola ataması) ile
      Türkçe ekleri ve büyük \`I/İ\` harflerini karşılayan alan sözcüklerini birlikte kullanır.
- [x] Hassas görev otomatik olarak council moduna genişletilmez; gerekçe plana yazılır.
- [x] Paylaşılacak sağlayıcılar ve veri, çalıştırmadan önce uyarıda ve dry-run tablosunda gösterilir.
- [x] Bulgu raporu yalnızca desenin adını ve sayısını taşır; eşleşen değer ekrana veya
      geçmişe hiç yazılmaz.

Kabul ölçütü: karşılandı. \`tests/test_classifier.py\` false-negative odaklı senaryoları,
\`tests/test_commander.py\` ise sessiz genişlemenin engellendiğini doğrular.

### P0 — Veri minimizasyonu (SEC-04) — **Tamamlandı**

- [x] \`--max-context\` karakter bütçesi (varsayılan 40.000) ve \`--lines 120-180\` bölüm seçimi.
- [x] Bütçe aşılınca dosyanın başı ve sonu korunur; aradan çıkarılan miktar hem modele
      bırakılan görünür bir işaretle hem de dry-run çıktısında bildirilir.
- [x] İkili, okunamayan, bulunamayan, dizin olan ve 5 MB üstü dosyalar için kontrollü hata.
- [x] Hassasiyet sınıflandırması artık dosyanın tamamını değil, sağlayıcıya *fiilen giden*
      kapsamı değerlendirir.

Kabul ölçütü: karşılandı. \`tests/test_context.py\` birden çok bütçe için
\`len(text) <= max_chars\` bağıntısını (kırpma işareti dâhil) doğrular;
\`tests/test_engine.py\` ise casus adaptörle sağlayıcıya ulaşan bağlamı ölçer.

### P0 — Katmanlı yapılandırma (FR-13) — **Tamamlandı**

- [x] Öncelik sırası: komut satırı > proje (`voltran.toml`) > kullanıcı > güvenli varsayılan.
- [x] Proje dosyası depo kökünde durur ve alt dizinlerden yukarı doğru aranır; `.voltran/`
      `.gitignore` içinde olduğu için yapılandırma oraya konmaz, ekiple paylaşılabilir kalır.
- [x] Bilinmeyen anahtar ve yanlış tür sessizce yok sayılmaz, `ConfigError` üretir.
- [x] `voltran config` yürürlükteki her ayarı ve **hangi katmandan geldiğini** gösterir
      (`--json` ile makinece okunabilir).
- [x] `--write` bilinçli olarak yapılandırılamaz; dosya değiştirme yetkisi her çalıştırmada
      açıkça verilmelidir, aksi hâlde "güvenli varsayılan" ilkesi anlamını yitirir.

Kabul ölçütü: karşılandı. `tests/test_config.py` katman önceliğini, keşif yürüyüşünü,
tür doğrulamasını ve yazma izninin yapılandırılamazlığını; `tests/test_cli.py` ise
`voltran config` çıktısını ve `run` üzerindeki etkisini doğrular.

### P0 — Git worktree yazma izolasyonu (SEC-07'nin ilk katmanı) — **Tamamlandı**

- [x] `--write` görevlerini aktif checkout yerine görev bazlı geçici worktree'de çalıştır.
- [x] Başlangıç ref'i olarak HEAD kullan; mevcut kirli değişiklikleri göreve taşımadan koru.
- [x] Görev sonunda binary patch ve test kanıtı üret; ana çalışma ağacına otomatik uygulama yapma.
- [x] Cleanup başarısızsa worktree yolunu koruyup kullanıcıya bildir.

Kabul ölçütü:

- Aktif çalışma ağacı görev sırasında değişmez.
- Success, failure, timeout ve cancel yaşam döngüleri testlidir.
- Kullanıcı incelemeden merge, cherry-pick veya patch uygulanmaz.

Sınır: Bu paket aktif checkout'u korur; üçüncü taraf CLI süreçlerinin worktree dışındaki her
dosyayı okumasını bütün sağlayıcılarda ortak bir OS politikasıyla engellemez. Bu nedenle paket
tamamlanmış olsa da üst gereksinim SEC-07 matriste **kısmi** kalır.

### P0 — Sağlayıcılar arası ortak dosya sandbox'ı (SEC-07) — **Planlandı**

- Worktree kökünü izin verilen tek yazma alanı yap; worktree dışı yolları üç adaptörde de reddet.
- Salt-okunur görevlerde yalnızca açıkça verilen bağlamı sağlayıcıya aç.
- Sembolik bağlantı, `..`, mutlak yol ve alt süreç üzerinden sınır aşma senaryolarını test et.
- Platform desteği yoksa `--write` işlemini güvenli biçimde reddet; sessizce zayıf moda düşme.

Kabul ölçütü: üç sağlayıcı için worktree dışındaki bir canary dosyası okunamaz ve değiştirilemez;
desteklenen macOS/Linux CI matrisinde sınır aşma testleri geçer.

## Sonraki paket: council doğruluğu ve dayanıklılığı

### P1 — Sınırlı council protokolü (FR-08, FR-09)

Durum: **Kısmi.** FR-08 tur ve bağlam sınırı ile FR-09 yapılandırılmış karar/itiraz
kaydı `2bbe784` ve `e6004f8` commitlerinde uygulandı.

- [x] Mesaj/tur, toplam süre ve toplam bağlam bütçesi koy.
- [x] Gerçek uzlaşma maddelerini supervisor durum metni yerine açık karar kaydından çıkar.
- [x] Çözülmeyen ajan itirazlarını nihai sentezde koru.
- Her ajanın başka bir ajanın katkısını gördüğünü olay kaydından doğrula.
- Uzlaşma için marker yanında katılımcı ve yanıt zinciri koşulu ara.
- Eksik sağlayıcı, ajan çökmesi ve kısmi sonucu ayrı durumlar olarak raporla.

Kabul ölçütü:

- Sonsuz konuşma mümkün değildir.
- Tek ajanın kendi kendine uzlaşma ilanı başarısızdır.
- Kısmi council hiçbir yüzeyde tam başarı görünmez.

### P1 — Yapılandırılmış uzman çıktısı (FR-10, FR-11)

Durum: **Kısmi.** Provider istemi ortak JSON sözleşmesini talep ediyor; düz, fenced ve
Antigravity stream yanıtları `TaskResult` alanlarına ayrıştırılıyor.

- [x] `summary`, `claims`, `evidence`, `uncertainties`, `risks`, `artifacts` ve `status`
  alanlarını sağlayıcıdan iste ve doğrula.
- [x] Şema dışı düz metin için geriye uyumlu fallback'i koru.
- Kanıt, belirsizlik, risk ve artifact alanlarını Markdown raporuna ekle.
- Şema uyumsuzluğunu metadata ve benchmark metriği olarak görünür yap.

Kabul ölçütü:

- Üç adaptörün yapılandırılmış ve düz metin yolları sözleşme testlerinden geçer.
- FR-11 alanları Markdown ve JSON raporlarında kaybolmaz.

### P1 — İptal, durum sözlüğü ve replay (FR-12, FR-15) — **Tamamlandı**

- [x] Ctrl-C sırasında provider ve hcom süreçlerini deterministik kapat (SIGINT -> SIGTERM/SIGKILL eskalasyonu, exit code 130).
- [x] `voltran cancel <run_id>` komutu ile devam eden çalışmayı ve arka plan süreç grubunu güvenle sonlandır.
- [x] SQLite `active_runs` tablosu ile aktif süreç ve PID takibi; iptal edilen çalışmanın `cancelled` durumuna geçirilmesi.
- [x] `voltran replay <run_id>` ile veritabanında saklanan özgün plan ve politikayı yeniden kurup yürütme (`--explain`, `--json`, `--output` destekli).
- [x] Geriye dönük uyumluluk: eski şemadaki veritabanlarını otomatik `plan_json` ve `policy_json` sütunlarıyla göç etme.
- [x] Replay gizli istem içeriğini geri yüklemez (sanitize edilmiş metin korunur).

Kabul ölçütü: karşılandı. `tests/test_cli.py` cancel, replay ve KeyboardInterrupt senaryolarını;
`tests/test_store.py` otomatik şema göçünü ve aktif çalıştırma yaşam döngüsünü;
`tests/test_engine.py` ise iptal çağrısının süreçleri sonlandırmasını doğrular.

### P1 — Gelişmiş bağlam sıkıştırması

- [x] Sabit ve ölçülebilir karakter bütçesi uygula.
- Sıkıştırmada kaynak olay kimlikleri ve kritik anlaşmazlıkları koru.
- Ham ve sıkıştırılmış transkript boyutlarını ölç.

Kabul ölçütü:

- Uzun oturum tanımlı üst sınırı aşmaz.
- Kritik hata ve anlaşmazlıklar sıkıştırmada kaybolmaz.

## 0.2 giriş kapısı: kalite

### P1 — Risk tabanlı test kapsamı

Öncelik: `hcom_client`, `lock`, `providers/cli`, `router`, `reporter`.

- [x] `hcom_client` kapsamı %65'ten **%94**'e çıkarıldı (`tests/test_hcom_client.py`).
- [x] `providers/cli` kapsamı %76'dan **%96**'ya çıkarıldı (`tests/test_providers.py`).
- [x] Satır kapsamına ek olarak timeout, yarış, bozuk çıktı ve cleanup dalları test edildi.
- [x] Toplam test sayısı 182'ye, proje kapsamı **%89.11**'e ulaştı.
- [x] CI kapsam alt sınırını %80'den %83'e çıkar.
- CI kapsam alt sınırını gerçek ölçüm %90'a ulaştığında %90'a çıkar.
- Gerçek model kotası CI'da tüketilmesin.

Kabul ölçütü:

- Toplam kapsam en az %90 (mevcut: %89).
- Riskli modüllerin her biri en az %85 (`hcom_client` %94, `providers/cli` %96).
- Ruff, Pyright strict ve tüm testler yeşil (182 test yeşil, 0 pyright hatası).

### P1 — Gerçek CLI uyumluluğu

- Desteklenen CLI sürümlerini belgeleyip fixture tabanlı sözleşme testleri ekle.
- Manuel veya nightly akışta gerçek version/help ve kısa smoke test çalıştır.
- Bilinmeyen sürümü sessizce hazır kabul etme.

## Daha sonra: gerçek benchmark

### P2 — Ölçülebilir değerlendirme

- Senaryoları sürümlü fixture dosyalarına taşı.
- Her görev için doğrulanabilir beklenen özellik veya test komutu tanımla.
- Quick/expert/council sonuçlarını aynı görev üzerinde karşılaştır.
- Çalıştırma başarısı ile cevap kalitesini ayrı metrikler olarak tut.
- En az 20 tekrar olmadan yüzde bazlı ürün iddiası yayımlama.

Kabul ölçütü:

- Veri seti, örneklem sayısı ve değerlendirme yöntemi raporda bulunur.
- Uzlaşma yalnızca açıkça doğrulanmış council sonucu için sayılır.
- Ölçülmemiş halüsinasyon azaltma iddiası yapılmaz.

## Ertelenen işler

- MCP tabanlı ortak araç katmanı.
- Kalıcı proje belleği veya vektör veritabanı.
- Kota dolunca otomatik checkpoint/resume.
- Menü çubuğu veya SwiftUI uygulaması.
- Otomatik GitHub PR yazma/gönderme.
- Gelişmiş yapılandırma katmanları ve yeni dağıtım kanalları.

Bunlar çekirdek güvenlik ve doğruluk sorunlarını çözmediği için yakın dönem taahhüdü değildir.

## Sürüm çıkış ölçütleri

### 0.1.x güvenilirlik sürümü

- Tüm P0 maddeleri tamamlanmış.
- Kalite kapıları yeşil.
- Dokümantasyonda kısmi özellikler tamamlanmış gösterilmiyor.

### 0.2.0

- P1 council, iptal, replay ve kalite maddeleri tamamlanmış.
- En az üç gerçek uçtan uca görevde hata ve cleanup doğrulanmış.
- Bilinen kritik veya yüksek öncelikli hata yok.

## Her değişiklikte çalıştırılacak kapılar

\`\`\`bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov=voltran --cov-report=term-missing --cov-fail-under=83
\`\`\`

Coverage alt sınırı gerçek ölçüm yükseldikçe artırılmalı; ölçüm artmadan hedef rakam
değiştirilmemelidir.
