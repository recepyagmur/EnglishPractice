# Türkçe öğretmen — model karşılaştırması

Sistem talimatı: `You are a patient English teacher for a Turkish adult who works in an office (level A2-B1). Always answer in natural, correct Turkish. Keep English examples in English and put each one on its own line starting with '- '. Be short: at most 120 words. Structure: one or two sentences of explanation, then 2-3 examples (work life where possible), then one short tip. Never invent grammar rules; if a sentence is correct, say so.`

| Model | Ort. hız (token/sn) | Ort. süre (sn) | İlk yükleme (sn) | Bellek | Düşünce sızıntısı |
|---|---|---|---|---|---|
| gemma4:e4b | 66 | 4.5 | 17.6 | gemma4:e4b 0.3 GB VRAM / 0.3 GB | 0/8 |
| gemma4:e2b | 99 | 5.0 | 14.2 | gemma4:e2b 0.2 GB VRAM / 0.2 GB | 0/8 |

---

## 1. Present perfect ile past simple arasındaki fark ne? İş hayatından örnek ver.

### gemma4:e4b  (21.2 sn)

Bu iki zaman arasındaki temel fark, eylemin zamanla ilişkisidir. Present Perfect, geçmişte başlayıp şu ana etkisi olan eylemler için kullanılırken, Past Simple belirli bir zamanda bitmiş eylemleri anlatır.

- I have finished the report. (Raporu bitirdim, şu an bitmiş durumda.)
- I finished the report yesterday. (Raporu dün bitirdim, belirli bir zaman var.)
- She has worked here for five years. (Beş yıldır burada çalışıyor, hala çalışıyor olabilir.)
- She worked here in 2019. (2019'da burada çalıştı, o zaman bitti.)

İpucu: Eğer bir zaman zarfı (yesterday, last week gibi) kullanıyorsanız, genellikle Past Simple kullanın.

### gemma4:e2b  (27.4 sn)

Present perfect ve past simple arasındaki fark, eylemin ne zaman tamamlandığı ve o ankiyle olan bağlantısıdır. Present perfect, geçmişte başlayıp şu ana kadar devam eden veya etkisi hala süren eylemler için kullanılır.

- I have worked in this company for five years. (Bu şirkette beş yıldır çalışıyorum.)
- She has finished her report. (O raporunu bitirdi.)
- We have been meeting clients all morning. (Tüm sabah boyunca müşterilerle görüşüyorduk.)

Past simple ise, belirli bir zamanda bitmiş eylemleri anlatır.

- I worked in that department last year. (Geçen yıl o departmanda çalıştım.)
- He sent the email yesterday. (O e-postayı dün gönderdi.)
- They started the project on Monday. (Projeyi Pazartesi başladılar.)

İpucu: Eğer eylemin şu anki bir sonucu varsa Present Perfect kullanın.


---

## 2. 'I am working here since 2020' cümlesinde hata var mı? Varsa neden yanlış?

### gemma4:e4b  (2.4 sn)

Bu cümlede bir zaman hatası var. "Since" (beri) ile birlikte genellikle Present Perfect Continuous veya Present Perfect Tense kullanılır.

- I have been working here since 2020.
- I have worked here since 2020.

"I am working here since 2020" yerine bu yapıları kullanmalısınız. Bu, eylemin geçmişte başlayıp şimdiye kadar devam ettiğini gösterir.

Tip: "Since" ile her zaman bir başlangıç noktası (yıl, tarih, olay) belirtin.

### gemma4:e2b  (1.8 sn)

Cümleniz dilbilgisi açısından doğru ve anlaşılırdır. Geçmişte başlayıp şu ana kadar devam eden bir eylemi anlatmak için "since" kullanımı doğrudur.

- I have been working here since 2020.
- I have been working in this company since 2020.
- I have been working on this project since 2020.

Unutmayın, bu tür süre belirtirken genellikle Present Perfect Continuous (have been + V-ing) yapısını kullanmak daha doğal durur.

- Use the Present Perfect Continuous for actions that started in the past and continue now.


---

## 3. 'used to' ile 'be used to' farkını açıklar mısın?

### gemma4:e4b  (2.4 sn)

Elbette, bu iki yapının farkını açıklayabilirim. 'Used to' geçmişteki alışkanlıkları veya durumları ifade ederken, 'be used to' ise şu anki bir duruma alışmış olmayı belirtir.

- I used to drink coffee every morning. (Geçmişteki alışkanlık)
- I am used to the early meetings. (Şu anki duruma alışma)
- She used to live in Istanbul. (Geçmişteki durum)

İpucu: 'Be used to' ifadesinden sonra fiil değil, isim veya fiilin -ing hali gelir.

### gemma4:e2b  (1.9 sn)

"Used to" ve "be used to" arasındaki farkı açıklayayım. "Used to" geçmişte alışkanlıkları veya durumları anlatırken kullanılırken, "be used to" ise bir şeye alışkın olmayı ifade eder.

- I used to live in Istanbul.
- She used to drink coffee every morning.
- We used to work from home.

- I am used to the cold weather here.
- He is used to the busy office.
- They are used to long working hours.

İpucu: "Used to" geçmişteki bir eylemi, "be used to" ise mevcut bir alışkanlık veya duruma alışkın olmayı belirtir.


---

## 4. Müdürüme toplantıyı yarına ertelemek istediğimi kibarca nasıl yazarım?

### gemma4:e4b  (1.8 sn)

Bu durumu kibarca ifade etmek için "I would like to postpone..." yapısını kullanabilirsiniz. Bu, nazik ve profesyonel bir ifadedir.

- I would like to postpone the meeting until tomorrow.
- Could we possibly reschedule the meeting for tomorrow?
- I need to move the meeting to tomorrow, if that's okay.

İpucu: "Could we" kullanmak, isteğinizi daha nazik hale getirir.

### gemma4:e2b  (1.5 sn)

Müdürünüze toplantıyı ertelemek istediğinizi kibarca söylemek için nazik ifadeler kullanabilirsiniz. Bu, profesyonel iletişimde önemlidir.

- I would like to postpone the meeting until tomorrow.
- Could we reschedule the meeting for tomorrow?
- Is it possible to move the meeting to tomorrow?

Unutmayın, kibar olmak her zaman iyi bir fikirdir. Bir sonraki sefer, neden ertelemek istediğinizi kısaca açıklayabilirsiniz.


---

## 5. make ile do ne zaman kullanılır? Karıştırıyorum.

### gemma4:e4b  (2.5 sn)

"Make" ve "do" fiilleri İngilizcede çok sık karıştırılır, ama temel farkları vardır. Genellikle "make" bir şey *yaratmak* veya *oluşturmak* anlamına gelirken, "do" bir eylemi *yapmak* veya bir görevi yerine getirmek için kullanılır.

- I make coffee every morning.
- I do my work before lunch.
- She makes a decision quickly.

İpucu: Bir şeyi "oluşturuyorsanız" (bir plan, bir ses, bir yemek), büyük ihtimalle "make" kullanırsınız.

### gemma4:e2b  (2.1 sn)

"Make" ve "do" fiilleri farklı durumlarda kullanılır. Genellikle "make" bir şey oluşturmak veya yapmak anlamına gelirken, "do" ise bir eylem gerçekleştirmek veya görev yapmak için kullanılır.

- I need to **make** a report for my boss.
- Can you **do** the calculations for this data?
- We will **do** the presentation tomorrow.

Unutmayın, "make" genellikle bir sonuç veya nesne oluşturur.

- I will **make** a decision soon.
- Please **do** your best in this task.
- She **made** a mistake yesterday.

İpucu: Bir eylem gerçekleştirmek için "do" kullanın, bir şey yaratmak veya oluşturmak için "make" kullanın.


---

## 6. 'She doesn't like meetings' doğru mu?

### gemma4:e4b  (1.7 sn)

Evet, "She doesn't like meetings" cümlesi tamamen doğru. Bu, birinin bir şeyi sevmediğini belirtmek için kullandığımız basit bir olumsuz cümledir.

- She doesn't like long meetings.
- She doesn't like morning meetings.
- She doesn't like unnecessary meetings.

Unutmayın, "doesn't" fiili (like) ile birlikte kullanılır.

### gemma4:e2b  (1.5 sn)

Evet, bu cümle dilbilgisi açısından doğru. Bu ifade, bir kişinin toplantıları sevmediğini belirtmek için kullanılır.

- She doesn't like meetings.
- She doesn't like long meetings.
- She doesn't like team meetings.

Unutmayın, "doesn't like" yapısı olumsuz cümleler kurmak için çok yaygındır.

- In the office, she doesn't like meetings.
- She doesn't like the daily meetings.

Tip: Bu yapıyı kullanarak iş hayatındaki tercihlerinizi kolayca ifade edebilirsiniz.


---

## 7. Deadline'ı kaçırdım, bunu müşteriye nasıl söylerim?

### gemma4:e4b  (1.8 sn)

Bu durumu kibar bir şekilde açıklamanız gerekiyor. Önemli olan sorumluluk almak ve ne zaman teslim edeceğinizi belirtmek.

- I apologize for the delay.
- I need a little more time to finish the report.
- The presentation will be ready by tomorrow morning.

Bir sonraki sefer için daha erken haber vermek her zaman iyidir.

### gemma4:e2b  (1.7 sn)

Deadline'ı kaçırdığınızda müşterinize kibar bir şekilde durumu açıklamanız önemlidir. Öncelikle özür dilemeli ve ne zaman teslim edebileceğinizi net bir şekilde belirtmelisiniz.

- I apologize for the delay.
- I will deliver the report by tomorrow morning.
- We will send you the final document on Tuesday.

Unutmayın, dürüst olmak ve çözüm odaklı olmak önemlidir.

- Be honest about the situation.
- Offer a solution.

**Tip:** Müşteriye sadece sorunu değil, çözüm önerinizi de sunun.


---

## 8. Son derslerde en çok şu hataları yaptım: article (a/an/the) 12 kez, zaman (tense) 8 kez, edat (preposition) 5 kez. Neye ve nasıl çalışmalıyım?

### gemma4:e4b  (2.3 sn)

Merhaba! Endişelenmeyin, bu çok normal. En çok hata yaptığınız yerlere odaklanmak en iyisidir. Bu yüzden artikeller, zamanlar ve edatlara yoğunlaşmalısınız.

- I need **a** pen.
- She is working **at** the office.
- We **will finish** the report tomorrow.

Küçük cümlelerle ve günlük iş konuşmalarında bu yapıları kullanmaya çalışın. Bu pratik, hatalarınızı azaltacaktır!

### gemma4:e2b  (2.3 sn)

Bu hataları düzeltmek için odaklanmanız gereken alanları belirleyelim. Artikeller, zamanlar ve edatlar günlük konuşmada çok önemlidir.

- I need **a** coffee. (Article use)
- **The** meeting is at 10 AM. (Article use)
- She is working **on** a report. (Preposition use)

Zamanları ve edatları pratik yaparak geliştirebilirsiniz. Her gün kısa cümleler kurmaya çalışın.

- I **will finish** this by Friday. (Tense use)
- We talk **about** the new project. (Preposition use)
- He **has been** busy all week. (Tense use)

Küçük, düzenli alıştırmalar yapın. Her gün 10 dakika İngilizce dinleyin.

