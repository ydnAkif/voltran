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

| Alan | Durum | Mevcut | Eksik |
| --- | --- | --- | --- |
| CLI ve paketleme | Tamamlandı | \`doctor\`, \`run\`, \`history\`, \`bench\`, \`dashboard\`, uv paketi ve macOS betiği | Tekrarlanabilir release süreci |
| Sağlayıcı adaptörleri | Kısmi | Codex, Claude ve Antigravity; timeout ve süreç temizliği | Sürüm uyumluluk matrisi ve gerçek CLI smoke testleri |
| Quick/expert | Kısmi | Router seçimi, timeout, normalize sonuç, hata raporu ve `--provider` izin listesi | Kullanıcı iptali (`voltran cancel`) ve paralel alt görev yürütme |
| Council | Kısmi | hcom oturumu, farklı sağlayıcılar, supervisor, açık uzlaşma işareti, izin listesine uyum ve "en az iki sağlayıcı" şartı | Tur/bağlam bütçesi, güçlü uzlaşma doğrulaması ve devam |
| Router | Kısmi | Yetenek, erişilebilirlik, moda göre puanlama ve doğrulanan sağlayıcı izin listesi | Kota, maliyet, gecikme ve oturum sağlığı |
| Gizlilik | Tamamlandı | Secret/PII maskeleme (giden ve kayıt yolu), hassasiyet sınıflandırması, hassas görevde otomatik council genişlemesinin engellenmesi, sağlayıcı izin listesi, dry-run veri paylaşım önizlemesi ve bağlam bütçesi/bölüm seçimi | SEC-01..SEC-04 karşılandı; kalan gizlilik işi yok |
| Yazma güvenliği | Kısmi | Atomik süreçler arası dosya kilidi; council'da tek yazıcı | Git worktree izolasyonu ve kontrollü diff uygulama |
| Raporlama | Kısmi | Markdown/JSON, rol, sağlayıcı, durum ve council güven alanları | Kanıtlar ve isteğe bağlı ham uzman çıktıları |
| Geçmiş | Kısmi | Maskelenmiş SQLite özeti ve son çalışmalar | Replay/resume |
| Benchmark | Kısmi | Üç sabit senaryo; durum, süre ve uzlaşma kaydı | Altın cevaplar, kalite değerlendirmesi ve karşılaştırmalı ölçüm |
| Test ve CI | Kısmi | Python 3.11–3.14, macOS/Linux, 99 test, %85 kapsam, CI kapsam kapısı %83 | `hcom_client` ve `providers/cli` için hedefli testler; %90 kapsam |
| Dashboard | Kısmi | Ajan, olay, kilit ve geçmiş görünümü | Hata dayanıklılığı ve uzun süreli kullanım testi |

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

### P0 — Git worktree yazma izolasyonu (SEC-07)

- \`--write\` görevlerini aktif checkout yerine görev bazlı geçici worktree'de çalıştır.
- Kirli çalışma ağacı ve başlangıç ref'i davranışını tanımla.
- Görev sonunda diff ve test sonucu üret; ana çalışma ağacına otomatik uygulama yapma.
- Cleanup başarısızsa worktree yolunu koruyup kullanıcıya bildir.

Kabul ölçütü:

- Aktif çalışma ağacı görev sırasında değişmez.
- Success, failure, timeout ve cancel yaşam döngüleri testlidir.
- Kullanıcı incelemeden merge, cherry-pick veya patch uygulanmaz.

## Sonraki paket: council doğruluğu ve dayanıklılığı

### P1 — Sınırlı council protokolü (FR-08, FR-09)

Durum: **Kısmi.** FR-08 tur ve bağlam sınırı ile FR-09 yapılandırılmış karar/itiraz
kaydı `21b74b0`, `2bbe784` ve `e6004f8` commitlerinde uygulandı.

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

### P1 — İptal, durum sözlüğü ve replay (FR-12, FR-15)

- Ctrl-C sırasında provider ve hcom süreçlerini deterministik kapat.
- Durumları tek sözlükte birleştir: success, partial, failed, timed_out, cancelled.
- \`voltran replay <run_id>\` ile kaydedilmiş plan/politikayı yeniden kur.
- Resume yalnızca güvenilir oturum devam kimliği kanıtlanırsa eklenir.

Kabul ölçütü:

- İptal sonrası artık süreç kalmaz.
- Benchmark, history, JSON ve Markdown aynı çalışma için çelişmez.
- Replay gizli istem içeriğini geri yüklemez.

### P1 — Bağlam bütçesi

- Önce sabit ve ölçülebilir karakter/token bütçesi uygula.
- Sıkıştırmada kaynak olay kimlikleri ve kritik anlaşmazlıkları koru.
- Ham ve sıkıştırılmış transkript boyutlarını ölç.

Kabul ölçütü:

- Uzun oturum tanımlı üst sınırı aşmaz.
- Kritik hata ve anlaşmazlıklar sıkıştırmada kaybolmaz.

## 0.2 giriş kapısı: kalite

### P1 — Risk tabanlı test kapsamı

Öncelik: \`hcom_client\`, \`lock\`, \`providers/cli\`, \`router\`, \`reporter\`.

- CI kapsam alt sınırını mevcut %80'den önce %85'e, sonra %90'a çıkar.
- Satır kapsamına ek olarak timeout, yarış, bozuk çıktı ve cleanup dallarını test et.
- Gerçek model kotası CI'da tüketilmesin.

Kabul ölçütü:

- Toplam kapsam en az %90.
- Riskli modüllerin her biri en az %85.
- Ruff, Pyright strict ve tüm testler yeşil.

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
uv run pytest --cov=voltran --cov-report=term-missing --cov-fail-under=80
\`\`\`

Coverage alt sınırı gerçek ölçüm yükseldikçe artırılmalı; ölçüm artmadan hedef rakam
değiştirilmemelidir.
