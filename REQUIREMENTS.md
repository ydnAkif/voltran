# VOLTRAN — Gereksinimler

Sürüm: `0.1-draft`

Durum: Başlangıç gereksinimleri

Hedef platform: macOS Apple Silicon (ilk sürüm)

## 1. Ürün hedefi

VOLTRAN, farklı LLM sağlayıcılarını tek bir yerel orkestrasyon katmanında birleştirmeli; kullanıcıya tek görev girişi, kontrollü görev dağıtımı ve tek sonuç raporu sunmalıdır.

Başarı ölçütü, daha fazla model çağırmak değil; tek modele kıyasla doğruluk, kapsam veya doğrulama kalitesini anlamlı biçimde artırırken süreyi, kotayı ve veri paylaşımını kontrol altında tutmaktır.

## 2. Kullanıcı gereksinimleri

### UR-01 — Tek görev girişi

Kullanıcı görevi bir kez yazabilmeli; hangi modele hangi alt görevin gönderileceğini elle düzenlemek zorunda kalmamalıdır.

### UR-02 — Önerilen mod

Sistem, görevi inceleyerek `quick`, `expert`, `council` veya `visual` modu önermeli ve önerisinin kısa gerekçesini göstermelidir.

### UR-03 — Elle geçersiz kılma

Kullanıcı önerilen modu, sağlayıcıyı veya rol dağılımını değiştirebilmelidir.

### UR-04 — Kurulum yardımı

Sistem eksik araçları belirlemeli, uygun kurulum komutlarını hazırlamalı ve kullanıcı onayıyla uygulamalıdır. Web tabanlı hesap girişlerinde kullanıcıya açık yönlendirme sağlamalıdır.

### UR-05 — Tek sonuç

Kullanıcıya birbirinden kopuk model cevapları yerine sentezlenmiş tek sonuç verilmelidir. İstenirse ham uzman çıktıları ayrıca görüntülenebilmelidir.

### UR-06 — Şeffaflık

Sonuç; kullanılan modelleri/sağlayıcıları, görev dağılımını, önemli anlaşmazlıkları, güven düzeyini ve varsa kaynakları göstermelidir.

### UR-07 — Türkçe önceliği

Arayüz ve varsayılan rapor dili Türkçe olmalı; görev diline göre otomatik geçiş desteklenmelidir.

## 3. İşlevsel gereksinimler

### FR-01 — Sistem teşhisi

`voltran doctor` aşağıdakileri kontrol etmelidir:

- macOS ve işlemci mimarisi
- Python çalışma zamanı
- `codex`, `claude` ve `agy` komutlarının varlığı; geçiş sürecinde eski `gemini` komutunun tespiti
- araç sürümleri
- oturum durumunu güvenli biçimde doğrulama imkânı
- gerekli yerel dizin ve dosya izinleri
- isteğe bağlı bağımlılıklar

Teşhis, varsayılan olarak değişiklik yapmamalıdır.

### FR-02 — Sağlayıcı adaptörleri

Her sağlayıcı şu ortak arayüzü uygulamalıdır:

- `availability()`
- `capabilities()`
- `health_check()`
- `execute(task, context, policy)`
- `cancel(run_id)`
- `normalize_result()`

İlk adaptörler Codex CLI, Claude Code CLI ve Google Antigravity CLI olacaktır. Eski
Gemini CLI yalnızca geçiş uyumluluğu için algılanacak; bireysel hesapların ana rotası
olarak kullanılmayacaktır.

### FR-03 — Yetenek keşfi

Router yalnızca model adına bakmamalı; adaptörün bildirdiği metin, kod, dosya, görsel, araç kullanımı, yapılandırılmış çıktı ve bağlam sınırı gibi yetenekleri değerlendirmelidir.

### FR-04 — Görev sınıflandırma

Komutan en az şu özellikleri çıkarmalıdır:

- görev türü
- karmaşıklık
- doğruluk riski
- gerekli araçlar
- paralelleştirilebilir alt görevler
- veri hassasiyeti
- tahmini süre/kota etkisi

### FR-05 — Plan üretimi

Plan, makinece doğrulanabilir bir veri yapısında tutulmalıdır. Her alt görev için kimlik, amaç, bağımlılık, aday rol, izin verilen sağlayıcılar, zaman aşımı ve beklenen çıktı şeması bulunmalıdır.

### FR-06 — Yönlendirme

Router seçim yaparken aşağıdaki sırayı dikkate almalıdır:

1. Gerekli yetenek
2. Veri paylaşım izni
3. Göreve uygunluk puanı
4. Erişilebilirlik ve oturum durumu
5. Kota/maliyet politikası
6. Gecikme tercihi

### FR-07 — Paralel yürütme

Bağımsız alt görevler eşzamanlı yürütülebilmeli; bir sağlayıcının hatası diğer görevleri otomatik olarak bozmamalıdır.

### FR-08 — Kontrollü model iletişimi

`council` modunda Claude, Codex ve Google Antigravity aynı orkestratör kontrollü konuşma
kaydını görmelidir. Her sağlayıcı diğerlerinin mesajlarına yanıt vermeli, itirazlarını
belirtmeli ve ortak çözümü geliştirmelidir. Konuşma sınırsız olmamalı; aktarılan mesajların
boyutu ve tur sayısı orkestratör tarafından sınırlandırılmalıdır.

Varsayılan sınırlar:

- ortak çalışma turu: 2
- nihai karar kaydı: 1
- kullanıcı onayı olmadan ek tur: 0

### FR-09 — Ortak çalışma ve sentez

`council` modunda üç sağlayıcı aynı görev üzerinde beraber çalışmalı; her biri en az bir
diğer sağlayıcının katkısını görerek yanıt üretmelidir. Nihai sentez ortak konuşmaya
dayanmalı ve çözülemeyen anlaşmazlıkları korumalıdır. Çoğunluk görüşü otomatik olarak
doğru kabul edilmemelidir.

### FR-10 — Çıktı sözleşmesi

Her uzman çıktısı en az şu alanları içermelidir:

- `summary`
- `claims`
- `evidence`
- `uncertainties`
- `risks`
- `artifacts`
- `status`

### FR-11 — Son rapor

Son rapor şunları içermelidir:

- doğrudan sonuç
- yapılan görev dağılımı
- kritik kanıt veya testler
- çözülemeyen anlaşmazlıklar
- güven düzeyi ve gerekçesi
- güvenli sonraki adım

### FR-12 — Geçmiş ve yeniden oynatma

Çalışmalar yerel veritabanında izlenebilmeli; kullanıcı aynı görevi aynı yapılandırmayla yeniden çalıştırabilmelidir. Gizli değerler kayda alınmamalıdır.

### FR-13 — Yapılandırma

Yapılandırma katmanları şu öncelikle birleştirilmelidir:

1. komut satırı seçeneği
2. proje yapılandırması
3. kullanıcı yapılandırması
4. güvenli varsayılanlar

### FR-14 — Kuru çalışma

`--dry-run`, hiçbir modele görev göndermeden planı, tahmini çağrı sayısını ve hangi verinin hangi sağlayıcıyla paylaşılacağını göstermelidir.

### FR-15 — İptal ve zaman aşımı

Kullanıcı devam eden çalışmayı iptal edebilmeli; alt süreçler düzgün kapatılmalı ve artık süreç bırakılmamalıdır.

## 4. Gizlilik ve güvenlik gereksinimleri

### SEC-01 — Gizli değer koruması

Parolalar, oturum çerezleri, erişim belirteçleri ve API anahtarları istemlere, günlük dosyalarına veya model çıktılarına yazılmamalıdır.

### SEC-02 — Sağlayıcı izin listesi

Her görev için kullanılabilecek sağlayıcılar açık bir politika ile sınırlandırılabilmelidir.

### SEC-03 — Hassas veri sınıflandırması

Finans, sağlık, kimlik, iletişim ve hesap verileri algılandığında sistem uyarı vermeli; `council` moduna otomatik genişleme yapmamalıdır.

### SEC-04 — Veri minimizasyonu

Tam dosya yerine mümkün olan en küçük ilgili parça uzmana gönderilmelidir.

### SEC-05 — Maskeleme

IBAN, kart numarası, T.C. kimlik numarası, telefon, e-posta ve benzeri alanlar için yerel maskeleme desteği sağlanmalıdır.

### SEC-06 — Komut güvenliği

Model çıktısı doğrudan kabuk komutu olarak çalıştırılmamalı; çalıştırılacak işlemler izin politikası ve kullanıcı onayı katmanından geçmelidir.

### SEC-07 — Dosya sınırları

Sağlayıcı süreçleri yalnızca görev için izin verilen dosya ve klasörlere erişebilmelidir.

## 5. İşlevsel olmayan gereksinimler

### NFR-01 — Platform

MVP, MacBook Air M1 sınıfı Apple Silicon cihazlarda çalışmalıdır.

### NFR-02 — Performans

- `voltran doctor` ağ beklemeleri hariç 5 saniye içinde yerel kontrolleri bitirmelidir.
- CLI, uzun görevlerde canlı durum bilgisi vermelidir.
- Bağımsız görevler eşzamanlı çalıştırılabilmelidir.

### NFR-03 — Dayanıklılık

Tek bir sağlayıcının bulunmaması veya hata vermesi sistemin tamamını çökertmemelidir. Uygun olduğunda plan yeniden yönlendirilmeli; değilse açık hata verilmelidir.

### NFR-04 — Test edilebilirlik

Sağlayıcı adaptörleri sahte süreçlerle test edilebilmeli; gerçek model kotası birim testler sırasında tüketilmemelidir.

### NFR-05 — Gözlemlenebilirlik

Her çalışma için benzersiz kimlik, süre, durum, seçilen rota ve hata türü kaydedilmelidir. İstemlerin tam içeriğini kaydetmek varsayılan olarak kapalı olmalıdır.

### NFR-06 — Genişletilebilirlik

Yeni bir sağlayıcı, çekirdek router değiştirilmeden adaptör kaydı yoluyla eklenebilmelidir.

### NFR-07 — Erişilebilir kullanım

Hata mesajları ve kurulum yönlendirmeleri teknik olmayan bir kullanıcının da takip edebileceği Türkçe açıklamalar içermelidir.

## 6. Mantıksal bileşenler

| Bileşen | Görev |
| --- | --- |
| CLI | Kullanıcı komutları ve canlı durum |
| Doctor | Ortam, araç ve oturum teşhisi |
| Commander | Görev analizi ve planlama |
| Router | Uzman/sağlayıcı seçimi |
| Executor | Paralel süreç çalıştırma ve iptal |
| Provider adapters | Sağlayıcıya özel komut ve çıktı normalizasyonu |
| Policy engine | Gizlilik, maliyet, tur ve izin sınırları |
| Critic/Judge | Eleştiri, karşılaştırma ve sentez |
| Store | Yerel yapılandırma, geçmiş ve ölçümler |
| Reporter | Markdown/JSON sonuç üretimi |

## 7. İlk bağımlılık kategorileri

Sürüm numaraları proje iskeleti oluşturulurken kilitlenecektir.

- CLI çatısı: Typer
- Terminal görünümü: Rich
- Veri doğrulama: Pydantic
- Yapılandırma: standart TOML desteği
- Veritabanı: SQLite
- Test: Pytest ve asyncio test desteği
- Kalite: Ruff veya eşdeğeri
- Tip denetimi: Pyright veya eşdeğeri
- Paketleme: `pyproject.toml` tabanlı modern Python paketi

## 8. MVP kabul kriterleri

MVP aşağıdaki senaryo başarıyla tamamlandığında hazır kabul edilir:

1. Kullanıcı `voltran doctor` çalıştırır ve üç CLI için anlaşılır durum raporu görür.
2. Kullanıcı tek bir görev girer.
3. Sistem görevi sınıflandırır ve mod önerir.
4. En az iki farklı sağlayıcı adaptörü başarıyla çağrılabilir.
5. `council` modunda üç sağlayıcı ortak transkript üzerinde en az iki tur çalışır.
6. Tek bir Markdown raporunda sonuç, anlaşmazlık ve güven düzeyi gösterilir.
7. Sağlayıcılardan biri başarısız olduğunda çalışma kontrollü biçimde devam eder veya anlaşılır biçimde durur.
8. Günlüklerde gizli bilgi bulunmadığını doğrulayan test geçer.
9. Gerçek model çağrısı yapmadan çalışan otomatik test paketi geçer.

## 9. Aşamalar

### Aşama 0 — Tanım

- README
- gereksinimler
- mimari kararların kaydı

### Aşama 1 — Sağlam temel

- Python proje iskeleti
- veri modelleri
- yapılandırma
- `voltran doctor`
- test/kalite hattı

### Aşama 2 — Sağlayıcılar

- ortak adaptör protokolü
- Codex CLI adaptörü
- Claude Code CLI adaptörü
- Google Antigravity CLI adaptörü
- sahte adaptör ve sözleşme testleri

### Aşama 3 — Orkestrasyon

- görev sınıflandırma
- planlama
- router
- paralel yürütme
- hata ve zaman aşımı yönetimi

### Aşama 4 — Konsey

- üç sağlayıcılı ortak konuşma
- karşılıklı eleştiri ve geliştirme turları
- ortak karar sentezi
- güven ve anlaşmazlık raporu

### Aşama 5 — Güvenlik ve değerlendirme

- hassas veri politikaları
- maskeleme
- denetim kayıtları
- görev bazlı değerlendirme seti
- rota kalite ölçümleri

### Aşama 6 — Dağıtım

- macOS kurulum komutu
- sürümleme
- güncelleme mekanizması
- isteğe bağlı SwiftUI arayüz araştırması

## 10. Açık kararlar

Aşağıdaki kararlar uygulama sırasında ölçüm veya kullanıcı tercihiyle netleştirilecektir:

- Paket yöneticisi: `uv`, Homebrew veya standart `venv`
- İlk dağıtım biçimi: Homebrew tap, `pipx` veya imzalı uygulama
- Varsayılan komutan sağlayıcısı
- Yerel istem saklama politikasının ayrıntıları
- Görsel üretim adaptörünün sağlayıcısı ve arayüzü
- API tabanlı isteğe bağlı adaptörlerin kapsamı
- SwiftUI arayüzünün MVP sonrası önceliği

## 11. Kapsam dışı — ilk sürüm

- Modellerin sınırsız veya gözetimsiz biçimde birbirleriyle konuşması
- Kullanıcı onayı olmadan satın alma, mesaj gönderme veya hesap işlemi
- Kullanıcı onayı olmadan ücretli API çağrısı
- Merkezi bulut hizmetinde kimlik bilgisi saklama
- Mobil iOS/iPadOS uygulaması
- Finansal işlem veya yatırım emri verme
- Her sağlayıcının tüm özelliklerini aynı arayüze zorla eşitleme
