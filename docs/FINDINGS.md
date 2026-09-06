# Bulgular: Yeşil CI ile gönderilen gerçek hatalar

Bu belge pazarlama metni değil, bu deponun kendi geçmişi. Buradaki her satır bir commit'e
dayanıyor ve doğrulanabilir.

## Neden var

VOLTRAN, düzenlediği üç modelin kendisi tarafından yazıldı: Claude, Codex ve Google
Antigravity. Geliştirme boyunca tekrarlayan tek bir örüntü ortaya çıktı:

> Bir model işini bitirdi, **"tamamlandı, testler geçiyor"** dedi, CI yeşildi, `pyright`
> strict modda sıfır hata verdi — ve kod yine de yanlıştı.

Aşağıdaki 16 hatanın **hiçbiri** testler tarafından yakalanmadı. Hepsi kod gerçek bir şeye
karşı çalıştırıldığında ortaya çıktı: gerçek bir süreç başlatılıp `pgrep` ile bakıldığında,
gerçek bir C++ dosyası maskeleme katmanından geçirildiğinde, gerçek bir Git deposu kurulup
masum bir süreç öldürtüldüğünde.

Bunun sebebi testlerin az olması değildi. Kapsam %83–89 aralığındaydı. Sebep şu: **bir model
kendi işini kendi testleriyle doğrulayınca, aynı yanlış varsayımı iki kez yazmış oluyor.**
Test, yazarın kafasındaki modeli doğrular; gerçeği değil.

## Bulgular

| # | Hata | Nasıl yakalandı | Düzelten |
| --- | --- | --- | --- |
| 1 | `voltran bench` **her zaman** "başarılı" diyordu. `has_failure and not report.executions` koşulu mantıken hiçbir zaman doğru olamaz — ölü kod. | Sahte bir motorla, tüm sağlayıcılar hata verirken çalıştırıldı; sonuç yine `success` geldi. | `d4d8a50` |
| 2 | Rapor tablosunda "Rol" sütunu rolü değil **sağlayıcı adını** basıyordu. Rol verisi `metadata` içinde duruyor ama hiç okunmuyordu. | Rapor üretilip çıktısına bakıldı. | `d4d8a50` |
| 3 | Council'da bir sağlayıcı eksikse, Router **aynı modeli iki role** atıyordu. Rapor üç ajan gösteriyordu, gerçekte iki tane vardı. | Claude kurulu değilmiş gibi davranan bir kayıtla çalıştırıldı. | `d4d8a50` |
| 4 | `health_check` zaman aşımında alt süreci **öldüremiyordu**. `killpg`, grup lideri olmayan bir PID'de `ProcessLookupError` verip sessizce dönüyordu. | Asılı kalan sahte bir CLI çalıştırıldı; zaman aşımından sonra süreç `pgrep` ile hâlâ ayaktaydı. | `d4d8a50` |
| 5 | `hcom` istemcisi zaman aşımında süreci sonlandırmadan hata fırlatıyordu — süreç sızıntısı. | Kod okuması; aynı sınıf hata (#4) ampirik olarak kanıtlandıktan sonra arandı. | `d4d8a50` |
| 6 | `FileLockManager.acquire`, uzun dosya yollarında yakalanmamış `OSError` fırlatıyordu. `pathlib` `ENAMETOOLONG` hatasını yutmuyor. | Derin bir dizin yoluyla kilit alınmaya çalışıldı; `voltran run --write` traceback ile çöktü. | `d4d8a50` |
| 7 | Python 3.14'te SQLite bağlantıları context manager'dan çıkınca kapanmıyor, `ResourceWarning` üretiyordu. | Codex'in kendi tam kontrol turunda buldu — listedeki tek öz-tespit. | `d4d8a50` |
| 8 | Türkçe noktasız `I` harfi kip algılamayı bozuyordu: `kıyasla` → council, **`KIYASLA` → expert**. Aynı kelime, sırf büyük harf yüzünden başka moda gidiyordu. | Anahtar kelimeler tek tek, büyük ve küçük harfle izole edilerek denendi. | `f8ac711` |
| 9 | Router'a dördüncü bir sağlayıcı eklenince `zip(..., strict=True)` **ValueError** ile çöküyordu. Kayıt modülünün docstring'i "yeni sağlayıcılar çekirdek değişmeden eklenebilir" diyordu. | Sahte bir dördüncü adaptör kaydedilip council çalıştırıldı. | `f8ac711` |
| 10 | Sağlayıcıya giden maskeleme **kaynak kodu bozuyordu**: `uint64_t x = 20231234567;` → `[REDACTED_TCKN]`. Model bozulmuş kodu inceliyor ve bunu fark etmiyordu. | Gerçek bir C++ parçası maskeleme katmanından geçirildi. | `f8ac711` |
| 11 | Çöken bir çalışmanın bıraktığı kilit **kalıcı** hâle gelmişti. UUID'li sahip kimliği + `O_EXCL` birleşince kimse kilidi açamıyordu; `voltran unlock` da yoktu. | Çöken süreç senaryosu kurulup yeni çalıştırma denendi. Bu bir **regresyondu** — iki ayrı düzeltmenin birleşmesinden doğdu. | `f8ac711` |
| 12 | `DB_PASSWORD=...` ve `APP_SECRET=...` **hiçbir zaman maskelenmiyordu** — ne modele giderken ne de yerel geçmişe yazılırken. Desendeki baştaki `\b`, önekli ortam değişkeni adlarını dışarıda bırakıyordu. Bu, ilk günden beri vardı ve üç inceleme turu boyunca gözden kaçtı. | Önekli ve öneksiz adlar yan yana denendi. | `f3eedf7` |
| 13 | Çıktı sözleşmesi kendisiyle çelişiyordu: istem modele `status=string` diyordu, kod ise `"success"` dışındaki her değeri **başarısızlık** sayıyordu. Sözleşmeye uyup `"ok"` yazan bir model başarısız görünüyordu. | Beş farklı `status` değeriyle çalıştırılıp sonuç tablosu çıkarıldı. | `e73e668`, `ac05dc5` |
| 14 | `voltran cancel`, veritabanındaki bayat bir PID'e doğrudan sinyal gönderiyordu. Çöken bir çalışma satırını geride bırakır, işletim sistemi o PID'i **başka bir uygulamaya** verir. | Masum bir `sleep` sürecine işaret eden bayat kayıt oluşturuldu; `voltran cancel` o süreci **öldürdü**. | `c52e73d` |
| 15 | Aynı komut `killpg` ile **tüm süreç grubuna** sinyal gönderiyordu. İş kontrolü olmayan bir kabukta VOLTRAN çağıranın grubunu miras alır — geçerli bir çalışmayı iptal etmek çağıran betiği de kapatırdı. PID geri dönüşümü gerekmiyor. | `sh -c` altında süreç grubu kimlikleri ölçüldü: çocuk, kabuğun grubunu miras alıyordu. | `c52e73d` |
| 16 | Yazma izolasyonunda model **bir sürümü okuyup başka bir sürümü düzenliyordu**: bağlam diskteki commit edilmemiş hâlden, worktree ise HEAD'den geliyordu. Ürettiği yama, akıl yürüttüğü koda ait değildi. | Gerçek bir Git deposu kirli çalışma ağacıyla kuruldu; casus bir adaptör modele ne gittiğini yakaladı. | `3732f46` |

## Yöntem

Listedeki 16 bulgunun 15'i incelemede, 1'i öz-kontrolde bulundu. Yakalama yöntemine göre
dağılım:

- **11 tanesi** kodu gerçek bir girdiye/sürece/depoya karşı **çalıştırmakla** bulundu.
- **3 tanesi** belge ile kodu karşılaştırmakla bulundu (docstring, istem metni, gereksinim
  belgesi neyi vaat ediyor — kod ne yapıyor).
- **2 tanesi** kod okumasıyla, ama yalnızca aynı sınıftan bir hata önce ampirik olarak
  kanıtlandığı için arandığından bulundu.

Hiçbiri mevcut testler tarafından yakalanmadı.

## Dürüstlük notu

Bu liste inceleyeni aklamak için değil. İnceleyen de aynı hataları yaptı:

- **#10** (maskelemenin kaynak kodu bozması) doğrudan inceleyenin kendi tavsiyesinden doğdu.
  "Giden veriyi de maskele" önerisi, dar bir desen seti şart koşulmadan uygulandı.
- **#11** iki ayrı düzeltmenin birleşmesinden doğan bir regresyondu; ikisi de tek başına
  doğruydu.
- Kirli ağaç uyarısı eklenirken uyarı yanlışlıkla **modelin kendi özetine** yazıldı; bunu
  mevcut bir council testi yakaladı ve düzeltildi (`3732f46`).

Çıkarım kişisel değil, yapısal: **kendi işini doğrulayan taraf, doğrulayan taraf sayılmaz.**
Kim olursa olsun.

---

*Bu belgeyi doğrulamak için: `git log --oneline` ve tablodaki commit kimlikleri.*
