# Deney 01 — Modeller işi kendileri bölebiliyor mu?

**Tarih:** _(koşulduğunda doldur)_
**Süre:** ~1 saat
**Kod yazılmadı. Bilinçli olarak.**

## Neden bu deney

Dört gün altyapı yazıp ona iş aradık. Bu sefer tersini yapıyoruz: önce ölçüyoruz, sonra
—gerekirse— yazıyoruz.

Test edilen varsayım, [arXiv 2603.28990](https://arxiv.org/html/2603.28990)'un iddiası:

> Ajanların rolü kendilerinin seçtiği düzen, merkezden tasarlanmış yapıdan daha iyi çalışır.
> Önceden rol atamak, insan kısıtlarını modellere kopyalamaktır.

Bu iddia 8 model ve 4–256 ajanla, API üzerinden ölçülmüş. **Bizim koşullarımız farklı:**
3 model, farklı üreticiler, tüketici aboneliği, saatlik kota, ve aralarında mesaj kanalı yok.
İddianın bu ölçekte tutup tutmadığını bilmiyoruz. Deney bunu soruyor.

Karşı kanıt olarak elimizde şu var: bu deponun ilk dört gününde roller **elle** dağıtıldı
(dosya sahipliği yazılı olarak verildi) ve iş yürüdü. Kendi kendine örgütlenme hiç denenmedi.
Yani iki yönde de test edilmemiş varsayım var.

## Tasarım

Modeller birbiriyle konuşamıyor. Bu yüzden 1. turda konuşturmuyoruz — **birbirinden habersiz,
aynı misyonu veriyoruz ve iş bölümü önerisi istiyoruz.** Öneriler örtüşüyorsa kendi kendine
örgütlenme mümkündür ve mesaj kanalı kurmaya değer. Örtüşmüyorsa değmez.

Bu, mesaj altyapısı kurmadan cevap veren en ucuz tasarım.

## Görev

5. sınıf Fen Bilimleri, aşağıdaki kazanım:

> **KAZANIM:** _(buraya önümüzdeki hafta gerçekten işlenecek kazanım yazılacak)_

Üretilecek içerik:

1. Kaynaklı bilgi metni (5. sınıf seviyesine uygun)
2. Bir görsel (üretim veya brief)
3. Beş soru
4. Cevap anahtarı ve puanlama
5. Bir sınıf etkinliği ve geri dönüt formu

## Misyon istemi

Üç modele de **aynen** bu metin verilir. Hiçbirine rol atanmaz, diğerlerinin ne yaptığı
söylenmez.

```
Bir ekipte çalışıyorsun. Ekipte üç yapay zekâ var: Claude, ChatGPT ve Gemini.
Hepsi bu mesajın aynısını aldı. Birbirinizle konuşamıyorsunuz.

ORTAK GÖREV
5. sınıf Fen Bilimleri dersi, şu kazanım için sınıfta kullanılabilir içerik:
[KAZANIM]

Üretilecekler: (1) kaynaklı bilgi metni, (2) bir görsel, (3) beş soru,
(4) cevap anahtarı ve puanlama, (5) bir etkinlik ve geri dönüt formu.

KISITLAR
- İçerik Türkiye'deki bir devlet ortaokulunda, 5. sınıfta kullanılacak.
- Bilimsel doğruluk ve kazanım uyumu her şeyin önünde.
- Sorular soru yazma tekniklerine uymalı.
- Hazırlayan öğretmen fen bilimleri öğretmeni; yüzeysel içeriği fark eder.

SENDEN İSTENEN — İÇERİĞİ HENÜZ ÜRETME
Önce şu üç soruyu cevapla:

1. Bu işi üç model arasında nasıl bölerdin? Her parçayı kim yapsın?
2. Bu bölümde SEN hangi parçayı alıyorsun ve neden? Diğer ikisinin yapamayacağı
   ya da senden daha kötü yapacağı ne var?
3. Üretilen işi kim, neye göre denetlesin? Hangi hataların çıkmasını bekliyorsun?

Kısa ve net yaz. Kendini övme, gerekçelendir.
```

## Ne ölçüyoruz

Koşmadan önce yazıldı. Sonradan değiştirilmeyecek.

| Ölçüm | Nasıl bakılır |
| --- | --- |
| **Yakınsama** | Üç öneri aynı iş bölümünü mü tarif ediyor? |
| **Çakışma** | Kaç model aynı parçaya talip? |
| **Boşluk** | Hiçbirinin sahiplenmediği parça var mı? |
| **Öz-farkındalık** | Model kendi zayıflığını doğru tespit ediyor mu, yoksa her şeye "ben iyiyim" mi diyor? |
| **Denetim tasarımı** | Denetleyiciyi kim önerdi, gerekçesi ne? |
| **Hata öngörüsü** | Öngörülen hatalar, sonradan gerçekten çıkanlarla örtüşüyor mu? |

## Karar kuralı — sonuç görülmeden yazıldı

- **BAŞARILI:** Üç öneri de aynı ya da uyumlu bir bölüm veriyor, çakışma yok veya bir tane.
  → Kendi kendine örgütlenme bizim ölçeğimizde çalışıyor. Mesaj kanalı kurulur, 2. tur yapılır.
- **KISMİ:** Bölüm mantıklı ama iki model aynı parçaya talip, ya da bir parça sahipsiz.
  → Tam otonomi değil; misyona minimum kısıt eklenip tekrar denenir.
- **BAŞARISIZ:** Öneriler birbirini tutmuyor, herkes her şeyi kendine alıyor, ya da
  gerekçeler içi boş ("ben yaratıcıyım" tarzı).
  → Araştırmanın iddiası bu ölçekte tutmuyor. Otonom iş bölümü fikri bırakılır,
  elle rol dağıtımına dönülür — ki bu deponun ilk dört gününde çalıştığı bilinen yöntem.

Hangi sonuç çıkarsa çıksın kayda geçer. **Başarısız sonuç da sonuçtur ve dört ay kazandırır.**

## Sonuçlar

_(koşulduktan sonra doldurulacak)_

### Claude'un önerisi

### ChatGPT'nin önerisi

### Gemini'nin önerisi

### Karşılaştırma

### Karar
