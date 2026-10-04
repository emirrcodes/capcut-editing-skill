# CapCut Editing Skill

CapCut Desktop projelerindeki sessiz veya konuşmasız kısımları kesmek ve anlama göre bölünmüş, düzenlenebilir altyazılar eklemek için yapay zekânızla kullanabileceğiniz bir skill. Video ve yalnız ses içeren projelerle çalışır. Ne yapmak istediğinizi normal bir mesajla söylersiniz; sonuç CapCut içinde düzenlenebilir kalır.

## Bu linki yapay zekânıza gönderin

Başlamak için [düz metin kurulum rehberini](https://ahmetemirarslan.com/capcut) kullandığınız yapay zekâya gönderip **“Bunu kullanmak istiyorum; neye ihtiyacım var ve nasıl kurarım?”** deyin. Rehber, GitHub sayfasına erişemeyen modeller için de gereksinimleri ve kurulum adımlarını doğrudan içerir. GitHub hesabınızın veya kod yazma bilginizin olması gerekmez.

Her sohbet servisi bağlantıları açamayabilir. Link açılamıyorsa rehberdeki metni kopyalayıp sohbete yapıştırın; aynı metin repoda [website/guide.txt](website/guide.txt) dosyasında da bulunur. Kurulum paketinin kaynağı bu GitHub reposudur.

İhtiyacınız olanlar:

- Bir bilgisayar ve üzerinde kurulu **CapCut Desktop**.
- Kullanacağınız yapay zekâ hizmetinde bir **hesap/üyelik**.
- İlk kurulum ve konuşma modelinin indirilmesi için internet bağlantısı ve yeterli boş disk alanı.

**Düzenlemeyi yapabilmek için yapay zekânın bilgisayarınızdaki dosyalara ve komut çalıştırmaya erişmesi gerekir.** Codex, Claude Code, Cursor veya Antigravity gibi yerel agentlarla çalışabilirsiniz. Yalnızca sohbet edebilen bir yapay zekâ da kurulumu açıklayabilir; yerel erişimi yoksa uygulayabileceğiniz adımları anlatmalı veya bu agentlardan birinde devam etmenize yardımcı olmalıdır. Linki göndermek tek başına otomatik kurulum yapmaz. Ekran, klavye veya fare kontrolü vermeniz gerekmez.

Python ve FFmpeg gibi yardımcı yazılımlar da gerekir; bunları önceden bilmeniz gerekmez. Agent eksikleri kontrol eder, erişimi varsa kurar, yoksa işletim sisteminize uygun adımları açıklar. macOS ve Windows için kurulum yolu vardır; Windows’ta native CapCut açıp kaydetme doğrulaması henüz tamamlanmamıştır.

**Antigravity / Gemini kullanıcıları:** Antigravity için `--agent antigravity` seçin. [Antigravity skill desteği](https://antigravity.google/docs/skills) ile proje kurulumu `.agents/skills/capcut-editing`, `--scope user` kurulumu `~/.gemini/config/skills/capcut-editing` yoluna yapılır. Bu seçenek Antigravity IDE/2.0 içindir; Antigravity CLI'ın global yolu farklıdır. [Google AI Pro](https://support.google.com/googleone/answer/14534406) ve [Ultra](https://support.google.com/googleone/answer/16286513) üyelikleri Antigravity'de daha yüksek kullanım limitleri sağlar. Gemini sohbeti tek başına yerel CapCut dosyalarını düzenleyemez. Antigravity kurulum yolları test edilmiştir; Antigravity agentıyla gerçek bir CapCut düzenlemesi henüz uçtan uca doğrulanmamıştır.

Bilgisayarda çalışabilen agentınıza yeni bir proje/klasör açıp şu mesajı gönderebilirsiniz:

> https://github.com/emirrcodes/capcut-editing-skill — Bu skilli bu projeye kur, eksik gereksinimleri kontrol et ve kullanıma hazır olup olmadığını söyle. Sonra CapCut projemin adını ve yapmak istediğim işlemi vereceğim.

## Bu README’yi okuyan yapay zekâ için

Kullanıcı yalnızca linki gönderdiğinde veya nasıl kullanılacağını sorduğunda önce amacı ve yukarıdaki gereksinimleri kullanıcının dilinde, teknik bilgi beklemeden açıklayın. İşletim sistemi veya kullanılan agent belli değilse gerekli bilgiyi öğrenin. Yerel dosya/terminal erişiminiz yoksa kurduğunuzu söylemeyin; kullanıcıya uygun yerel agentta devam etme veya manuel kurulum yolunu anlatın. Eksik gereksinimler için yalnız mevcut adımı çözmesini sağlayan talimatı verin.

Kullanıcı kurulumu istediğinde:

1. Public repoyu ayrı bir paket klasörüne indirin; kullanıcının mevcut çalışma dosyalarının üzerine yazmayın. GitHub girişi veya Git zorunlu değildir; ZIP indirme de kullanılabilir. `skills/capcut-editing/SKILL.md` dosyasını okuyun.
2. Python **3.10+** kurulu mu kontrol edin; eksikse işletim sistemine uygun kurulum yolunu izleyin. Gerçekte kullandığınız agentı seçerek `python install.py --agent claude|cursor|codex|antigravity --project <kullanıcının-proje-klasörü>` çalıştırın. `claude|cursor|codex|antigravity` yerine tek doğru değeri yazın. Varsayılan kurulum yalnız bu projeye yapılır; başka bir agent için destek varmış gibi davranmayın.
3. FFmpeg’i kontrol edin; eksikse kullanıcının işletim sistemine uygun kurulum yolunu izleyin. Kurulan skillde `scripts/setup.py` çalıştırın. Bunun bildirdiği virtualenv Python’ı ile `scripts/capcut_tool.py doctor` çalıştırın. Dosya/ağ erişimi için çalıştığınız ortamın izinlerine uyun.
4. Skillin keşfedildiğini, gerekli ses motorunu, FFmpeg’i ve kullanılabilir fontu doğrulayın. Skill listede görünmüyorsa kurulan proje klasöründe yeni oturum açılmasını açıklayın. Gerçek eksikleri belirtin; yalnız dosyaların kopyalanmasını “kullanıma hazır” diye sunmayın.
5. Kullanıcıya kurulduğu klasörü, hazır olan işlemleri ve aşağıdaki üç komutu kısa biçimde anlatın. İlk konuşmasız kesim/altyazı isteğinde yerel modelin indirileceğini ve daha uzun sürebileceğini söyleyin. Kurulum sırasında CapCut projesini değiştirmeyin. Düzenleme istediğinde güncel projeyi okuyun; yazarken yalnız hedef projenin kaydedilip kapalı olması gerekir, CapCut açık kalabilir.

## Kullanım

```text
“proje adı” sessiz kısımları kes
“proje adı” konuşmasız kısımları kes
“proje adı” altyazı ekle
```

| Komut | Ne yapar? |
| --- | --- |
| **sessiz kısımları kes** | Ses seviyesine göre keser: varsayılan eşik **−30 dBFS**, minimum sessizlik **80 ms**; sıkı kesim varsayılandır. |
| **konuşmasız kısımları kes** | Sıkı kesim varsayılandır: konuşma taraması, kelime kontrolü ve tüm timeline’da duraklama incelemesi; 80 ms boşluk eşiği ve 30 ms kenar payı. “Konuşma olmayan kısımları kes” de bu komutu çalıştırır. |
| **altyazı ekle** | Mevcut timeline'a anlamlı, genellikle 4–6 kelimelik altyazılar ekler. |

Birlikte de isteyebilirsiniz: `“proje adı” konuşmasız kısımları kes ve altyazı ekle` veya `“proje adı” sessiz kısımları kes ve altyazı ekle`.

Agent, mevcut CapCut timeline'ını okur; birleşik istekte kesim ve altyazıyı birlikte hazırlar, doğrular ve uygular. Arada manuel kontrol zorunlu değildir. Sonuç CapCut içinde düzenlenebilir kalır. Proje adı belirsizse klasör yolunu verin. Yazma sırasında **işlem yapılacak proje kaydedilip kapatılmış olmalı**; CapCut ana ekranda veya başka bir projede açık kalabilir. Agent hedef projenin kapalı olduğunu doğrular; işlemden sonra projeyi yeniden açın. Ekran/klavye/fare kontrolü gerekmez, yerel dosya ve komut erişimi gerekir.

**Konuşmasız kesim ses yüksekliğine göre karar vermez.** Yerel [Silero VAD](https://github.com/snakers4/silero-vad) modeli konuşma bölgelerini bulur. Aday konuşmasız aralıklar çevrelerindeki sesle birlikte tekrar taranır; düşük sesli bölümler analiz sırasında güçlendirilerek de kontrol edilir. İkinci geçişte bulunan olası konuşma korunur. Kelime kenarlarında varsayılan 30 ms pay bırakılır; korumalar sonrasında kalan, doğrulanan 80 ms ve üzeri konuşmasız aralıklar kesilir. Bu, fan/trafik gibi gürültüyü konuşmadan ayırmayı amaçlar; başka konuşmalar veya şarkı da konuşma sayılabilir. Amaçlanan konuşmacıyı tek başına ayırma garantisi yoktur. Hiç konuşma bulunmazsa tüm videoyu silmek yerine işlem durur.

**Konuşmasız kesimde ayrıntılı kontrol varsayılan olarak açıktır.** Agent güncel sesin Whisper kelime zamanlarını VAD ile karşılaştırır, tüm timeline’ı örtüşen bağlamlarda inceler ve kesim adayını yeniden transkribe ederek gerçek kaynak aralıklarının korunduğunu doğrular. Uzayan kelime zamanlarının sakladığı boşluklarda, boşluğun iki tarafını ayrıca tarayarak kelimenin yerini kontrol eder. Belirsiz heceler, konuşmalar, tekrarlar ve yarım başlayan cümleler korunur; kalan aralıkların gerekçeleri raporda görünür. Daha sıkı kesim için ayrıca komut vermeniz gerekmez. Bu inceleme altyazı eklemez; yerel transkripsiyon modeli gerektirir ve ilk kullanım daha uzun sürebilir. Transkripsiyonda eksilen kelime tek başına sesin silindiği anlamına gelmez. 100 ms minimum çıktı klibi, 80 ms duraklama eşiğinden ayrıdır.

Zayıf kelimelerin başını korumak için farklı bağlamlarda doğrulanan kısa kelimelerin kaynak aralıkları ayrıca kontrol edilir. Kesilmiş seste aynı kelimenin tanınması, bütün hecelerinin kaldığını kanıtlamaz. Altyazıda uzun veya birden fazla kesimi aşan kelime zamanları ayrıca incelenir; konuşulan tekrarlar ve yarım başlayan cümleler korunur. Kesimden gereğinden erken başlayan altyazılar inceleme tamamlanmadan yazılmaz.

**Doğal duraklamaları korumak isterseniz** agentınıza söyleyin. references/natural-pauses.config.json sessizlikte 250 ms, konuşmasız kesimde 300 ms boşluk ve 120 ms kenar payı kullanır; konuşma koruma kontrolleri açık kalır. Her iki profil de kayda ve tercihinize göre revize edilebilir.

Varsayılan altyazılar Türkçe, küçük harf, beyaz ve siyah konturludur. Anlamlı bloklar genellikle **4–6 kelime**, en fazla 6 kelimedir; kısa tam ifadeler daha kısa olabilir. Altyazılar boşluksuz ilerler. Klip sınırları iki yönde kontrol edilir: soldaki metin sağ klibe taşmamalı, sağdaki metin solda erken görünmemelidir. İki konuşma bloğu arasındaki boşlukta video kesimi varsa iki altyazı tam kesimde buluşur; sağ kelimenin biraz sonra başlaması soldaki metni uzatmak için gerekçe değildir. Aynı klip içindeki boşluklar doğal kelime başlangıcına kadar doldurulur. Erken zamanlanmış sağ kelime için 0.25 saniyelik kesim hizalaması da korunur. Konuşma klipler arasında devam ediyorsa doğal ifade sınırları korunur; birden fazla aday kesim veya belirsiz sahiplik ayrıca incelenir.

Kelime sayısı, dil, büyük/küçük harf, noktalama, font, boyut, renk, konum, sessizlik ve konuşma algılama ayarları değiştirilebilir. Agentınıza tercihinizi söyleyin; references/config.example.json üzerinden dışarıda bir ayar dosyası oluşturabilir. Kullanıcı tercihleri varsayılanların önündedir.

**Sessizlik kesme ses seviyesine dayanır:** FFmpeg `silencedetect=noise=-30dB:d=0.08`; arası ≤0.12 saniye sessizlikler birleştirilir, <0.10 saniye kalan parçalar atılır. Ortam gürültüsü varsa gürültülü konuşmasız bölümleri kaçırabilir; eşiği yükseltmek alçak sesli konuşmayı da kesebilir. Böyle kayıtlarda konuşmasız kesim komutunu tercih edebilirsiniz.

**Ortam sesine göre agentla konuşarak revize edebilirsiniz.** Fan, trafik, müzik veya mikrofon dip sesi olduğunu söyleyin; gerekirse kesilecek aralıkları daha detaylı incelemesini isteyin. Agent seçilen yöntemin eşiğini, kelime kenarı paylarını ve kısa duraklamaların korunmasını kayda göre değerlendirebilir. İlk sonuç fazla sert veya fazla temkinliyse yedekten geri dönüp yeni ayarlarla hazırlamasını isteyebilirsiniz. Tek bir ayar her ortama uymaz.

```text
“Bu kayıtta fan sesi var; konuşmasız kısımları kes, şüpheli aralıkları detaylı incele”
“Ortam sesi çok yüksek; VAD ile kelime zamanlarını birlikte kontrol et”
“Konuşma uçlarını koruyarak daha kısa duraklamaları da kes”
“Kelime sonları fazla kesiliyor; daha temkinli ayarlarla yeniden hazırla”
“Kısa doğal duraklamaları koru, uzun sessizlikleri kes”
```

## CapCut otomatik altyazısına göre avantajı

CapCut’ın otomatik altyazı aracı konuşmayı metne dönüştürür; oluşan metni ve görünümü uygulamada düzenleyebilirsiniz. Gürültü, aksan veya hızlı konuşma nedeniyle yanlış tanınan kelimeler için metni gözden geçirip düzeltmek gerekir. [CapCut’ın açıklaması](https://www.capcut.com/help/auto-captions-in-capcut).

Bu skillde transkripsiyondan sonra **kullandığınız AI agentın modeli altyazıyı bağlamıyla birlikte gözden geçirir**. Yanlış tanınan kelimeleri, anlam kaymalarını ve bozulmuş ifadeleri kontrol eder; açık hataları konuşmanın bağlamına göre düzeltir, belirsiz bölümleri güncel ses üzerinden ayrıca inceler. Altyazıları anlama göre kısa ifadelere böler ve klip kesimleriyle zamanlamasını kontrol eder. Böylece transkripsiyona ek olarak bağlam ve anlam incelemesi de iş akışına dahil olur. Amaç konuşulanı doğru aktarmaktır; agent yeni içerik uydurmamalı veya konuşmayı yeniden yazmamalıdır.

**Altyazıyı kendi komutlarınızla şekillendirebilirsiniz.** Kelime sayısını, anlamlı bölünme kurallarını, dili, harf kullanımını, noktalamayı ve görünümü agentınıza söyleyin. Varsayılan 4–6 kelimelik bloklar, küçük harf ve klip sınırı kuralları bu tercihlerin başlangıç noktasıdır. Örneğin:

```text
“proje adı altyazı ekle; transkripsiyon hatalarını bağlama göre kontrol et, konuşulanı değiştirme”
“Blok başına en fazla 4 kelime kullan; cümleyi anlamlı yerlerden böl, fiili tek başına bırakma”
“Altyazıları küçük harf yap ve sondaki noktalama işaretlerini kaldır”
“Altyazıları biraz büyüt; beyaz yazı ve siyah kontur kullan”
```

## Platformlar ve manuel kurulum

- **Apple Silicon macOS:** MLX Whisper veya CPU üzerinde faster-whisper.
- **Windows / Intel macOS:** faster-whisper; varsayılan CPU, NVIDIA/CUDA isteğe bağlıdır. Windows yol, kurulum ve transkripsiyon desteği vardır; **Windows CapCut’ta açıp yeniden kaydetme doğrulaması henüz tamamlanmamıştır**.
- Python **3.10+**, FFmpeg, kullanılabilir bir font ve yerel dosya/komut erişimi gerekir. Agent bunları kontrol eder; CapCut ile gelen font kullanılabilir.

Setup installs CPU Silero VAD through [faster-whisper](https://github.com/SYSTRAN/faster-whisper), plus MLX Whisper when selected, in an isolated virtualenv. The small VAD model comes with that dependency. Default speech cutting uses Whisper for word/pause review even without captions; its model downloads on first speech-cut or caption use. Amplitude-only silence cutting needs no transcription model. Detection and transcription run locally; model files are not included in this repository. Once a local agent reads the generated transcript, that text is subject to the agent provider's ordinary data handling.

Kurulumu kendiniz yapmak isterseniz **Code → Download ZIP** ile indirip çıkarın, sonra:

```sh
python install.py --agent codex --project /path/to/your/project
# agent değeri: codex, claude, cursor veya antigravity; Windows’ta gerekirse py -3 kullanın
```

Yalnız skilli bütün projelerde kullanmak istiyorsanız `--scope user` seçin. `--replace`, önceki kurulumu zaman damgalı bir yedekte korur. FFmpeg ayrı kurulur. Kurulumdan sonra kurulan skillin `scripts/setup.py` dosyasını çalıştırın; bildirdiği Python ile `scripts/capcut_tool.py doctor` çalıştırarak hazır olduğunu kontrol edin. Ayrıntılı düzenleme ve geri alma komutları [workflow.md](skills/capcut-editing/references/workflow.md) içindedir.

## Supported drafts and backups

Supports readable JSON draft_info.json or draft_content.json layouts and detected full-draft mirrors in a single timeline. All detected full copies must agree before an edit. Cutting supports one forward 1.0x media track and optional previous codex_subtitles. Multi-track cutting, speed ramps, reversed/animated primary clips, transitions, encrypted drafts, and unknown schemas are rejected. Subtitle-only editing preserves user text tracks and replaces only codex_subtitles.

Cutting checks the pieces created at existing clip boundaries, not only global keep ranges. To prevent new clips below 100 ms, it keeps a little extra audio within the same original clip and reports those intervals. Existing short clips stay whole. Direct cutting and final validation reject new or shortened micro-clips; discontinuous source ranges are never joined into one continuous clip to bypass the check.

Every apply/restore creates timestamped backups before project writes. Source fingerprints prevent applying stale work. A failed write attempts recovery; crashes or storage failures may still need restore from the manifest. Keep the reported backup suffix. Successful apply retains a local diagnostics_archive beside its work directory, containing settings, source fingerprints and analysis evidence, before cleaning managed temporary files. Transcript review originals/evidence and independent caption review audio remain for inspection; remove them only when authorized. The cleanup command handles abandoned preparations. Keep these personal diagnostic files outside the tracked skill package. No export/render of the final video is included.

The subtitle template contains schema/style defaults only: no personal project text, paths, footage, font binaries, or account identifiers. Compatibility is constrained by CapCut's changing draft format. Automated tests use synthetic projects; they do not prove compatibility with every CapCut version. This is an independent project, not an official CapCut product.

## Development

```sh
python -m pip install "faster-whisper>=1.2.1,<2"
python -m unittest discover -s tests -v
python skills/capcut-editing/scripts/capcut_tool.py doctor
```

Tests cover real FFmpeg cuts, bundled VAD rejection of loud noise, weak-word protection, independent checks of suspicious ASR repetitions, three-millisecond clip-boundary regressions, preserved existing short clips, post-write validation/rollback, separate speech/caption modes, caption timing, stale-plan refusal, alternate layouts, and all four agent installers. Transcription adapters are tested without downloading Whisper weights. Native CapCut/Windows round trips should be recorded separately before changing the compatibility claims.

MIT licensed. See [LICENSE](LICENSE).
