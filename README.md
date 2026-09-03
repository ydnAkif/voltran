# VOLTRAN

[![CI](https://github.com/ydnAkif/voltran/actions/workflows/ci.yml/badge.svg)](https://github.com/ydnAkif/voltran/actions/workflows/ci.yml)

**Birden fazla yapay zekâ modelini, tek bir görevin uzman parçaları olarak birleştiren yerel orkestrasyon sistemi.**


VOLTRAN; kullanıcıdan tek bir görev alır, görevi uygun uzmanlara böler, sonuçları kontrollü turlarla karşılaştırır ve tek bir denetlenebilir cevap üretir. Amaç, üç modele aynı soruyu sorup üç ayrı cevap göstermek değil; her modeli gerçekten katkı sağlayacağı yerde kullanmaktır.

## Projenin amacı

- GPT/Codex, Claude ve Gemini ailesini ortak bir görev akışında çalıştırmak.
- Basit işleri hızlı modellere, zor işleri güçlü modellere yönlendirmek.
- Modellerin birbirlerinin sonuçlarını inceleyebilmesini sağlamak.
- Çelişkileri, kaynakları ve güven düzeyini son raporda göstermek.
- Kullanıcının mevcut ChatGPT Plus, Claude Pro ve Google AI Pro erişimlerinden mümkün olduğunca yararlanmak.
- Kullanıcının açık onayı olmadan ücretli API kullanımına geçmemek.

## Temel çalışma biçimi

```mermaid
flowchart TD
    U["Kullanıcının görevi"] --> M["Komutan / Router"]
    M --> W["Uzman işçiler"]
    W --> C["Eleştiri ve doğrulama"]
    C --> J["Hakem ve sentez"]
    J --> R["Tek sonuç raporu"]
```

### Roller

| Rol | Sorumluluk |
| --- | --- |
| Komutan | Görevi anlamak, parçalamak, risk ve hassasiyet düzeyini belirlemek |
| Router | Uygun sağlayıcıyı/modeli yetenek, süre ve kota durumuna göre seçmek |
| Uzman işçi | Kodlama, araştırma, belge analizi, görsel inceleme veya rutin alt görevi yürütmek |
| Eleştirmen | Hataları, eksikleri, çelişkileri ve dayanaksız iddiaları bulmak |
| Hakem | Aday sonuçları karşılaştırmak ve anlaşmazlıkları çözmek |
| Raportör | Ortak sonucu, belirsizlikleri ve kaynakları tek çıktıda sunmak |

Model adları rollere kalıcı olarak kilitlenmez. Örneğin Claude çoğu kod görevinde güçlü bir aday olabilir; ancak router görev tipine, mevcut model sürümüne, bağlama ve yapılan ölçümlere göre seçim yapar.

## Çalışma modları

### `quick` — Voltran Hızlı

Tek ana model ve gerekirse bir hızlı yardımcı kullanır. Küçük kod değişiklikleri, özetleme, sınıflandırma ve biçimlendirme için.

### `expert` — Voltran Uzman

Komutan, göreve en uygun bir veya iki uzmanı çağırır. Kodlama, teknik teşhis ve kapsamlı belge analizi için varsayılan mod.

### `council` — Voltran Konsey

Claude, Codex ve Google Antigravity ortak bir konuşma kaydı üzerinde tur bazlı olarak
çalışır. Her sağlayıcı diğerlerinin görüşlerini okuyup yanıtlar, çözümü geliştirir ve ekip
tek bir uygulanabilir sonuç üretir. Finans, önemli kararlar, mimari tasarım ve yüksek
doğruluk gereken işler için.

### `visual` — Voltran Görsel

Metin ekibi görsel brifi hazırlar; uygun görsel sağlayıcısı üretim veya düzenleme yapar. Bu mod, ilgili sağlayıcının kullanılabilir görsel aracına göre etkinleşir.

## İlk sürümün kapsamı (MVP)

1. macOS Apple Silicon üzerinde çalışan `voltran` komutu.
2. Resmî CLI adaptörleri:
   - Codex: `codex exec`
   - Claude Code: `claude -p`
   - Google Antigravity CLI: `agy -p`
3. Sağlayıcı erişilebilirlik ve oturum kontrolü.
4. `quick`, `expert` ve `council` modları.
5. Paralel alt görev çalıştırma, zaman aşımı ve hata izolasyonu.
6. JSON tabanlı ortak görev/yanıt sözleşmesi.
7. Yerel SQLite çalışma geçmişi ve denetim kaydı.
8. Hassas veri uyarısı, sağlayıcı izin politikası ve isteğe bağlı maskeleme.
9. Tek Markdown sonuç raporu.

MVP’de masaüstü arayüzü, bulut sunucusu, otomatik API harcaması ve sınırsız ajan sohbeti bulunmayacak.

## Tasarım ilkeleri

- **Yerel öncelikli:** Orkestratör ve kayıtlar kullanıcının Mac’inde çalışır.
- **Abonelik öncelikli:** Önce resmî CLI oturumları; API anahtarları yalnızca ayrıca seçilirse.
- **Sağlayıcı bağımsız:** Çekirdek, tek bir modelin komut biçimine bağlı olmaz.
- **En az veri:** Her uzmana yalnızca ihtiyaç duyduğu bağlam gönderilir.
- **Açık izin:** Hassas belgelerin hangi sağlayıcılarla paylaşılacağı görünür ve kontrol edilebilir olur.
- **Sınırlı tartışma:** Varsayılan olarak en fazla bir çözüm ve bir eleştiri turu; sonsuz model konuşması yoktur.
- **Denetlenebilirlik:** Hangi görevin hangi modele neden verildiği kaydedilir.
- **Ölçülebilirlik:** Model seçimi kişisel kanaatten çok görev bazlı değerlendirmelerle iyileştirilir.

## Önerilen teknoloji yığını

- Python 3.11+
- `asyncio` ve güvenli alt süreç yönetimi
- Typer tabanlı CLI
- Pydantic tabanlı veri sözleşmeleri
- SQLite tabanlı yerel kayıt
- Pytest tabanlı testler
- Daha sonraki aşamada isteğe bağlı SwiftUI masaüstü arayüzü

Kesin paket sürümleri, ilk kurulum sırasında Mac’teki mevcut Python ve paket yöneticisi kontrol edildikten sonra kilitlenecektir.

## Kullanım ve Komutlar

### 🩺 Sistem Teşhisi (`voltran doctor`)
Ortamı, gerekli araçları (`codex`, `claude`, `agy`) ve oturum durumunu hiçbir değişiklik yapmadan denetler:
```bash
uv run voltran doctor
# Makinece okunabilir JSON çıktısı için:
uv run voltran doctor --json
```

### ⚡ Görev Yürütme (`voltran run`)
Komutan görevi analiz ederek uygun çalışma modunu (`quick`, `expert`, `council`) ve modelleri otomatik seçer:
```bash
# Otomatik mod seçimi ile çalıştırma:
uv run voltran run "Sistem mimarisini karşılaştır ve riskleri listele"

# Kota harcamadan plan ve sağlayıcı dağılımını önizleme:
uv run voltran run "Veritabanı şemasını optimize et" --dry-run --explain

# Belirli bir modda, zaman aşımı ve bağlam dosyasıyla çalıştırma:
uv run voltran run -m council --timeout 60 "Sistem mimarisini karşılaştır ve riskleri listele"
uv run voltran run --mode expert --file app.py "Bu kodun güvenlik açıklarını incele"

# Sonuç raporunu Markdown dosyasına veya JSON formatına kaydetme:
uv run voltran run "JSON çıktısını özetle" --mode quick --output rapor.md
uv run voltran run "Hızlı analiz" --json
```

### 💡 Kolay Erişim (Global Kurulum)
`uv run` yazmadan doğrudan `voltran` komutunu kullanmak isterseniz:
```bash
uv tool install . --force
# veya geliştirme modunda:
pip install -e .
```
Artık terminalden doğrudan çalıştırabilirsiniz:
```bash
voltran run -m council "Mimariyi karşılaştır"
voltran history
```

### 📜 Çalışma Geçmişi (`voltran history`)
Yerel SQLite veritabanındaki son çalışmaları listeler:
```bash
uv run voltran history
```

### 🔜 Geliştirilmekte Olan Komutlar
```bash
voltran login codex
voltran login claude
voltran login google
voltran config
```

## Geliştirme ve Test

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -v
```


## Güvenlik sınırı

VOLTRAN, bir dosyayı birden fazla sağlayıcıya gönderdiğinde veri fiilen birden fazla hizmetle paylaşılmış olur. Bu nedenle finansal, sağlıkla ilgili veya kimlik bilgisi içeren dosyalarda varsayılan politika şudur:

1. Hassas veri sınıflandırması yap.
2. Gereksiz kimlik alanlarını maskele.
3. Yalnızca gerekli parçaları seç.
4. Kullanılacak sağlayıcıları işlem öncesinde göster.
5. Kullanıcı onayı yoksa kapsamı genişletme.

Parolalar, oturum belirteçleri ve API anahtarları model istemlerine veya çalışma kayıtlarına yazılmaz; yerel SQLite veritabanına kaydedilmeden önce otomatik olarak maskelenir (`[REDACTED_API_KEY]`, `[REDACTED_TOKEN]`, `[REDACTED_EMAIL]`, `[REDACTED_CARD]`).

## Yol haritası

- [x] Proje adı ve temel vizyon
- [x] İlk gereksinimlerin tanımlanması
- [x] Proje iskeleti ve test altyapısı
- [x] `voltran doctor`
- [x] Ortak sağlayıcı adaptör arayüzü
- [x] Codex, Claude ve Google Antigravity CLI adaptörleri
- [x] Router ve çalışma modları (`quick`, `expert`, `council`)
- [x] Üç sağlayıcılı, ortak transkriptli konsey görüşmesi
- [x] Yerel SQLite çalışma geçmişi (`voltran history`)
- [x] Gizlilik koruması ve veri maskeleme (API key, token, PII)
- [x] Hata ve zaman aşımı izolasyonu (`--timeout`, süreç iptali)
- [ ] Görev bazlı değerlendirme seti
- [ ] Paketleme ve tek komutluk macOS kurulumu
- [ ] İsteğe bağlı SwiftUI arayüz


## Resmî teknik dayanaklar

- [OpenAI — Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [OpenAI — Orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)
- [OpenAI — Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [Anthropic — Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Google — Antigravity CLI](https://antigravity.google/product/antigravity-cli)
- [Google — Gemini CLI geçiş duyurusu](https://github.com/google-gemini/gemini-cli/discussions/28017)

## Durum

Çekirdek orkestrasyon mekanizması (`quick`, `expert`, `council` modları, komutan, yönlendirici ve tek sonuç raporlama) tamamlanmıştır. `voltran run` ve `voltran history` komutları yerel olarak test edilebilir durumdadır.
