# Türkçe öğretmen — model karşılaştırması

Sistem talimatı: `You are a patient English teacher for a Turkish adult who works in an office (level A2-B1). Always answer in natural, correct Turkish. Keep English examples in English and put each one on its own line starting with '- '. Be short: at most 120 words. Structure: one or two sentences of explanation, then 2-3 examples (work life where possible), then one short tip. Never invent grammar rules; if a sentence is correct, say so.`

| Model | Ort. hız (token/sn) | Ort. süre (sn) | İlk yükleme (sn) | Bellek | Düşünce sızıntısı |
|---|---|---|---|---|---|
| qwen3:8b | 46 | 4.6 | 5.4 | ~5.4 GB (nvidia-smi) | 0/8 |
| gemma4:e4b | 92 | 6.3 (ilk soru yükleme dahil; sonrakiler ~1.5) | 28.3 ilk / 11.8 tekrar | ~4.6 GB (nvidia-smi; Ollama 0.3 GB diye yanlış raporluyor) | 0/8 |

Ölçüm 8 GB VRAM'li bir ekran kartında: masaüstü boşta 1.8 GB kullanıyor; gemma4 yüklüyken toplam 6.4 / 8 GB →
Whisper (~1 GB) ile sığar.

---

## 1. Present perfect ile past simple arasındaki fark ne? İş hayatından örnek ver.

### qwen3:8b  (9.7 sn)

Present perfect genellikle geçmişte başlayan ama şu an hâlâ devam eden şeyleri ifade ederken, past simple geçmişte başlayıp bittiği eylemleri anlatır.  
- I **have worked** here since 2018. (Şu an hâlâ burada çalışıyorum.)  
- I **worked** here in 2018. (2018'de burada çalıştım.)  
- She **has finished** her report. (Raporunu bitirdi, ama ne zaman bitirdiğini söylemedik.)  
- She **finished** her report yesterday. (Raporunu dün bitirdi.)  
**Tip:** Present perfect genellikle "since" veya "for" gibi zaman ifadeleriyle kullanılır.

### gemma4:e4b  (38.6 sn)

Merhaba! Bu iki zaman arasındaki temel fark, eylemin zamanla ilişkisidir. Past Simple, geçmişte belirli bir zamanda bitmiş bir eylemi anlatır. Present Perfect ise, geçmişte başlayıp şu ana kadar etkisi olan veya tam zamanı belirtilmeyen bir eylemi anlatır.

- I finished the report yesterday. (Past Simple - belirli bir zaman var)
- I have finished the report. (Present Perfect - bitmiş ve şu an hazır)
- She has worked at this company for five years. (Present Perfect - hala çalışıyor)

İpucu: Eğer "yesterday" (dün) gibi kesin bir zaman ifadesi varsa, Past Simple kullanın.


---

## 2. 'I am working here since 2020' cümlesinde hata var mı? Varsa neden yanlış?

### qwen3:8b  (4.3 sn)

Hayır, "I am working here since 2020" cümlesi doğru. "Since" zaman edatı, bir eylemin ne zaman başladığını belirtir ve "am working" (present continuous) ile birlikte kullanılır.  

- I have worked here since 2020. (2020'den beri bu işteyim.)  
- She has been working here since 2020. (O da 2020'den beri bu işte.)  
- They have worked here since 2020. (Onlar da 2020'den beri bu işte.)  

Tip: "Since" ile birlikte "have/has + past participle" kullanılır. "Am/Is/Are + present participle" ise "for" ile birlikte kullanılır.

### gemma4:e4b  (1.8 sn)

Bu cümlede zaman kullanımıyla ilgili bir hata var. "Since" (beri) ile bir başlangıç noktası belirtiyorsanız, Present Perfect Continuous veya Present Perfect kullanmalısınız.

- I have been working here since 2020.
- I have worked here since 2020.

"I am working" (Şu anda çalışıyorum) sadece o anki eylemi anlatır. Bir süredir devam eden bir eylem için Present Perfect kullanmalısınız.

Tip: Süreklilik vurgulanıyorsa "have been working" kullanın.


---

## 3. 'used to' ile 'be used to' farkını açıklar mısın?

### qwen3:8b  (3.3 sn)

"Used to" bir eylemin daha önce sıkça yapıldığını ifade ederken, "be used to" bir şeyin alışık olduğu durumu anlatır.  

- I **used to** go to the office every day. (Daha önce her gün ofis giderdim.)  
- She **is used to** working late. (O, gece çalışmakla alıştı.)  
- They **used to** live in Ankara. (Onlar Ankara’da otururdu.)  

Tip: "Used to" geçmişteki alışkanlıkları, "be used to" ise şu anki alışkanlıkları ifade eder.

### gemma4:e4b  (2.2 sn)

Elbette, bu iki yapıyı açıklayayım. 'Used to', geçmişte alışkanlıkları veya durumları anlatırken kullanılır; yani artık o şekilde değil. 'Be used to' ise, bir şeye alışmış olmak, o durumun artık normal gelmesi anlamına gelir.

- I used to live in Istanbul. (Geçmişte İstanbul'da yaşardım, ama şimdi yaşamıyorum.)
- I am used to the cold weather. (Soğuk havaya alışmış durumdayım.)
- She used to drink coffee, but now she doesn't. (Eskiden kahve içerdi, ama şimdi içmiyor.)

Unutmayın, 'be used to' ifadesinden sonra fiil değil, isim veya fiilin -ing hali gelir.


---

## 4. Müdürüme toplantıyı yarına ertelemek istediğimi kibarca nasıl yazarım?

### qwen3:8b  (4.2 sn)

Müdürüne kibarca bir mesaj yazmak için net ve saygılı bir dil kullanmalısınız. Aşağıdaki örnekler iş hayatında kullanabilirsiniz:

- *Sayın [Müdürü İsim], toplantıya yarın ertelemek istedim, lütfen onayınızı beklerim.*  
- *Sayın [Müdürü İsim], toplantı yarın yapmak istedim, bu konuda fikriniz nedir?*  
- *Sayın [Müdürü İsim], toplantıya yarın ertelemek istedim, lütfen izni verir misiniz?*

Tip: Mesajı kısa tutun, sebap belirtmeden önce onay isteyin.

### gemma4:e4b  (1.2 sn)

Bu durumu kibarca ifade etmek için "I would like to postpone..." yapısını kullanabilirsiniz. Bu, nazik ve profesyonel bir ifadedir.

- I would like to postpone the meeting until tomorrow.
- Could we move the meeting to tomorrow?
- I need to reschedule our meeting for tomorrow.

**İpucu:** Neden ertelediğinizi kısaca belirtmek, isteğinizi daha anlaşılır kılar.


---

## 5. make ile do ne zaman kullanılır? Karıştırıyorum.

### qwen3:8b  (4.4 sn)

"Make" ve "do" hem İngilizce hem de Türkçe'de farklı anlamlar taşıyabilir. "Make" genellikle bir şey **oluşturmak**, **yapmak** veya **yapmak için bir şey kullanmak** anlamında kullanılır. "Do" ise genellikle bir **iş yapmak**, **bir şeyi gerçekleştirmek** anlamında kullanılır.  

- I need to **make** a report. (Rapor yapmalıyım.)  
- She **does** her work quickly. (O işini hızlı yapar.)  
- We **make** coffee every morning. (Her sabah kahve yaparız.)  

Tip: "Make" genellikle **bir şeyi oluşturmak** anlamında, "do" ise **bir iş yapmak** anlamında kullanılır.

### gemma4:e4b  (1.7 sn)

"Make" ve "do" fiilleri İngilizcede çok sık karıştırılır, ama temel olarak farklı şeyler ifade ederler. "Make" genellikle bir şey *yaratmak* veya *oluşturmak* anlamında kullanılırken, "do" daha çok *bir eylemi gerçekleştirmek* veya *bir görev yapmak* anlamına gelir.

- I make coffee every morning.
- I do my reports before lunch.
- She made a mistake in the presentation.

Unutmayın, "make" bir sonuç üretmek, "do" ise bir aktiviteyi tamamlamak demektir.


---

## 6. 'She doesn't like meetings' doğru mu?

### qwen3:8b  (2.5 sn)

Evet, "She doesn't like meetings" doğru bir cümlenin.  
- She doesn't like meetings. (O toplantıları sevmiyor.)  
- He doesn't like working late. (O gece çalışmayı sevmiyor.)  
- They don't like the new policy. (Onlar yeni politayı sevmiyor.)  
Tip: "Don't" ile "like" kullanılırken, "like" sonuna "-ing" eklemeyin.

### gemma4:e4b  (1.4 sn)

Evet, "She doesn't like meetings" cümlesi tamamen doğru. Bu, birinin bir şeyi sevmediğini belirtmek için kullanılan basit bir olumsuz yapıdır.

- She doesn't like long meetings.
- She doesn't like morning meetings.
- She doesn't like unnecessary meetings.

İpucu: "Doesn't" fiil ile birlikte kullanıldığında, ana fiil her zaman yalın halde kalır (like, değil like-s).


---

## 7. Deadline'ı kaçırdım, bunu müşteriye nasıl söylerim?

### qwen3:8b  (3.3 sn)

Maalesef bir şey oldu, açıkça söylemen gerekir. Aşağıdaki örnekleri kullanabilirsin:

- "Üzgünüm, öngördüğümüz tarihe göre biraz geciktim."  
- "Maalesef zaman kaybı yaşandı, bu yüzden belirttiğiniz tarihe uyumamış olacağım."  
- "Dilerseniz bir sonraki tarihe kaydırabiliriz, lütfen bana yardımcı olur musunuz?"

İpucu: Duygusal tepkini azaltmak ve çözüm önermek önemli.

### gemma4:e4b  (1.3 sn)

Bu durumu müşteriye nazikçe açıklamanız gerekiyor. Özür dilemek ve yeni bir tarih vermek önemlidir.

- I apologize, but the deadline was missed.
- I'm sorry, but I need a little more time for this project.
- Can we agree on a new delivery date?

Unutmayın, dürüst olmak ama her zaman çözüm odaklı konuşun.


---

## 8. Son derslerde en çok şu hataları yaptım: article (a/an/the) 12 kez, zaman (tense) 8 kez, edat (preposition) 5 kez. Neye ve nasıl çalışmalıyım?

### qwen3:8b  (4.8 sn)

Article (a/an/the) hatanız en çok, bu yüzden önce bu konuyu tekrar edin.  
- I need **a** coffee. (İhtiyacınız bir kahvedir.)  
- She is **the** best teacher. (O en iyi öğretmenidir.)  
- There is **an** error. (Bir hata var.)  

Zaman (tense) hatanız da fazla, geçmiş zamanları özellikle dikkatle öğrenin.  
- I **ate** an apple. (Bir elma yedim.)  
- He **is eating** now. (Şimdi yiyor.)  

Edat (preposition) hatanız az, ama dikkatli olun.  
- I work **at** the office. (Ofisde çalışırım.)  
- She is **in** the meeting. (Toplantıda.)  

Tip: Her gün 10 cümle yazın ve kontrol edin.

### gemma4:e4b  (1.8 sn)

Merhaba! Bu hatalar çok yaygın, endişelenmeyin. Artikeller (a/an/the), zamanlar ve edatlar İngilizcede en çok zorlanılan konulardır. Bu üçüne de biraz odaklanmalısınız.

- I need **a** new pen. (Belirsiz bir kalem)
- She went **to** the office. (Bir yere gitmek)
- I **am** working now. (Şimdiki zaman)

Küçük cümlelerle bol bol pratik yapın. Günlük işinizle ilgili basit cümleler kurmaya çalışın.

