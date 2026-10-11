"""Hand-picked useful phrases for the ready-made scenarios (shown in the session report).

Curated instead of generated: a small local model tends to suggest the other
person's lines or the learner's own mistakes. Each entry: (phrase, Turkish meaning, example).
"""

PHRASES = {
    "job_interview": [
        ("I have … years of experience in …", "… konusunda … yıllık deneyimim var",
         "I have three years of experience in backend development."),
        ("I was responsible for …", "…'dan sorumluydum", "I was responsible for the payment system."),
        ("One of my strengths is …", "Güçlü yönlerimden biri …", "One of my strengths is solving problems quickly."),
        ("I'm looking for a role where …", "… bir pozisyon arıyorum",
         "I'm looking for a role where I can learn new technologies."),
        ("Could you tell me more about the team?", "Ekip hakkında biraz daha bilgi verebilir misiniz?",
         "Could you tell me more about the team I would work with?"),
        ("What does a typical day look like?", "Tipik bir gün nasıl geçiyor?",
         "What does a typical day look like for a developer here?"),
    ],
    "restaurant": [
        ("Could I see the menu, please?", "Menüyü görebilir miyim, lütfen?", "Hi, could I see the menu, please?"),
        ("What do you recommend?", "Ne tavsiye edersiniz?", "Everything looks good. What do you recommend?"),
        ("Does this dish contain …?", "Bu yemekte … var mı?", "Does this dish contain nuts? I'm allergic."),
        ("I'd like …, please.", "… alayım, lütfen.", "I'd like the grilled chicken and a lemonade, please."),
        ("Could we have the bill, please?", "Hesabı alabilir miyiz, lütfen?", "That was delicious. Could we have the bill, please?"),
        ("Can I pay by card?", "Kartla ödeyebilir miyim?", "Can I pay by card, or is it cash only?"),
    ],
    "airport": [
        ("I'm here on holiday / on business.", "Tatil / iş için buradayım.", "I'm here on holiday for two weeks."),
        ("I'll be staying at …", "…'da kalacağım.", "I'll be staying at a hotel in central London."),
        ("I'm visiting a friend.", "Bir arkadaşımı ziyaret ediyorum.", "I'm visiting a friend who lives in Manchester."),
        ("My return flight is on …", "Dönüş uçuşum … tarihinde.", "My return flight is on the 20th of May."),
        ("Here is my passport.", "Buyurun, pasaportum.", "Good morning. Here is my passport."),
        ("Could you repeat that, please?", "Tekrar eder misiniz, lütfen?", "Sorry, could you repeat that, please?"),
    ],
    "hotel": [
        ("I have a reservation under the name …", "… adına rezervasyonum var.",
         "Hello, I have a reservation under the name Yılmaz."),
        ("What time is breakfast served?", "Kahvaltı saat kaçta veriliyor?", "What time is breakfast served in the morning?"),
        ("Is Wi-Fi included?", "Wi-Fi dahil mi?", "Is Wi-Fi included in the price?"),
        ("Could I have a quiet room, please?", "Sessiz bir oda alabilir miyim, lütfen?",
         "Could I have a quiet room, please? I'm a light sleeper."),
        ("What time is check-out?", "Çıkış saati kaçta?", "What time is check-out on Sunday?"),
        ("The … isn't working.", "… çalışmıyor.", "Excuse me, the air conditioning in my room isn't working."),
    ],
    "doctor": [
        ("I've had a … for … days.", "… gündür …", "I've had a headache for three days."),
        ("I've got a sore throat.", "Boğazım ağrıyor.", "I've got a sore throat and a slight fever."),
        ("It hurts when I …", "…-dığımda acıyor.", "It hurts when I swallow."),
        ("I'm allergic to …", "…'ya alerjim var.", "I'm allergic to penicillin."),
        ("How often should I take it?", "Ne sıklıkla almalıyım?", "How often should I take this medicine?"),
        ("Should I come back if it gets worse?", "Kötüleşirse tekrar gelmeli miyim?",
         "Should I come back if it gets worse?"),
    ],
    "small_talk": [
        ("Nice to meet you. I'm …", "Tanıştığımıza memnun oldum. Ben …", "Nice to meet you. I'm Ali."),
        ("So, what do you do?", "Peki, ne iş yapıyorsun?", "So, what do you do? Are you a developer too?"),
        ("How did you hear about this event?", "Bu etkinliği nereden duydun?", "How did you hear about this event?"),
        ("That sounds interesting! Tell me more.", "Kulağa ilginç geliyor! Biraz daha anlat.",
         "That sounds interesting! Tell me more about your project."),
        ("I'm really into …", "…'ya gerçekten ilgi duyuyorum.", "Me too! I'm really into machine learning."),
        ("It was great talking to you.", "Seninle konuşmak çok güzeldi.",
         "It was great talking to you. See you at the next meetup!"),
    ],
    "tech_meeting": [
        ("I'd like to suggest …", "… önermek istiyorum.", "I'd like to suggest a new way to handle errors."),
        ("The main benefit is that …", "Ana faydası şu: …", "The main benefit is that pages will load faster."),
        ("This would help us …", "Bu, …mize yardımcı olur.", "This would help us find bugs earlier."),
        ("That's a good point.", "Haklı bir nokta.", "That's a good point. I hadn't thought about that."),
        ("I see your concern, but …", "Endişeni anlıyorum ama …", "I see your concern, but the risk is quite low."),
        ("Shall we try it in a small pilot first?", "Önce küçük bir pilotla deneyelim mi?",
         "Shall we try it in a small pilot first and see the results?"),
    ],
    "return_product": [
        ("I bought this … last week.", "Bu …'ı geçen hafta aldım.", "I bought these headphones here last week."),
        ("It stopped working after …", "… sonra çalışmayı bıraktı.", "They stopped working after two days."),
        ("Here is my receipt.", "Buyurun, fişim.", "Here is my receipt."),
        ("I'd like a refund, please.", "Para iadesi istiyorum, lütfen.", "I'd like a refund, please."),
        ("Could I exchange it for a new one?", "Yenisiyle değiştirebilir miyim?",
         "If a refund isn't possible, could I exchange it for a new one?"),
        ("I'm sorry, but that's not acceptable.", "Kusura bakmayın ama bu kabul edilemez.",
         "I'm sorry, but that's not acceptable. They're only a week old."),
    ],
}
