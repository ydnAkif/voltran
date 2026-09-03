# ADR-0001: Python CLI mimarisi

- Durum: Kabul edildi
- Tarih: 2026-09-03

## Bağlam

MVP; macOS Apple Silicon üzerinde çalışan, resmî sağlayıcı CLI'larını güvenli alt süreçler
olarak yöneten ve gerçek model çağrısı olmadan test edilebilen yerel bir komut satırı aracı
gerektiriyor.

## Karar

- Paket düzeni `src/voltran` olacak ve Python 3.11+ destekleyecek.
- CLI Typer, terminal sunumu Rich ve veri sözleşmeleri Pydantic ile oluşturulacak.
- Sağlayıcı süreçlerini çalıştırma kodu bağımlılık enjeksiyonuyla test edilebilir tutulacak.
- İlk uçtan uca parça, hiçbir dosya veya hesap durumunu değiştirmeyen `voltran doctor` olacak.
- Yapılandırma ve çalışma verisi birbirinden ayrı dizinlerde tutulacak.

## Sonuçlar

Bu seçim hızlı bir MVP ve güçlü sözleşme testleri sağlar. Typer, Rich ve Pydantic çalışma
zamanı bağımlılıklarıdır; paket sürümleri `uv.lock` ile yeniden üretilebilir biçimde
kilitlenecektir.

