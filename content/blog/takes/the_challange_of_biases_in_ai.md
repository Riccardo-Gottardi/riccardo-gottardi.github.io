---
title: The Challange of Biases in AI
---

This blog post hold the content of a short paper I wrote for the University course in "Social, Ethical and Legal aspects of Artificial Intelligence and Cybersecurity" (part of my Master program at the Alpen Adria University of Klagenfurt). In that short paper I analysed and discussed the problems that biases pose to the world of AI.

# Introduction

## Definition of Bias

A bias is defined, by the Cambridge dictionary, as "The action of supporting or opposing a particular person or thing in an unfair way, because of allowing personal opinions to influence your judgment" In other words biases are metal models. Mental models are not bad in "per sè", they are the tool, we, as living beings, use to interpret the world that surround us. The fact of being potentially problematic, comes directly from their nature. Being the result of personal experience, they are subjective and the experience of someone might be different from the one of someone else, as often is. Since they are not subjective, they, might not represent the "truth". As conveyed by the definition given by the Cambridge dictionary, biases have a negative connotate. Indeed, they are used to refer to those mental models, that, in a sense, "warp" the reality, giving an interpretation of it that does not represent the "truth" of that simply is not objective. That can lead to different phenomenon, such as discrimination, interpretation of events based on personal values or else.

## Biases in the Context of AI

When it comes to the world of AI (Artificial Intelligence), the same holds. However, the concept of bias is expanded in three main categories: input, system and application bias [Hof25]. They differ in the time in which they enter in the AI system. 

**Input biases** are built into the data, therefore, they are learned by the model as part of the task. They might be the result of an unbalance samples distribution among the different class, if we are talking about a classification model, or a text conveying a specific point of view, if we are talking about LLMs (Large Language Models). 
To better understand this type of bias, lets introduce an example, taking into account a regressor model. The task is: "Given the characteristics of a person, such as age, height, ethnicity, ..., predict whether or not the person is a potential criminal". If the training dataset is unbalanced, and for instance, the ethnicity distribution among the samples labelled as "potential criminal" is not uniform (so there is an ethnicity that hold most of them). The regressor will learn that pattern and classify people with certain ethnicity as "potential criminal" more often than others. In the example the dataset was biased and the system was subject to input bias.

**System biases** are introduced by the system design and training process.
Recalling the example above, of the regression model, lets suppose that our dataset was ordered alphabetically, based on the ethnicity of the samples. If no shuffling is done before splitting the dataset, into training and test set, and the split is done as, the first n and the last m, an entire ethnicity (or a big part of it) might end up excluded from the training data. Therefore, the model will potentially label the sample with the excluded ethnicity as "potential criminal" with a lower rate than it should be, with an obvious consequence on the model performance.

**Application biases**, are introduced after deployment, and they mainly come from the way the AI system is used and. 

In addition to the main distinction above, biases can be further divided in: uninten-tional and intentional.

**Unintentional bias** coincide with input bias, inherited from the training dataset. They where not intended to be part of the system, some of them can be avoided, like the ones related to unbalanced dataset, whereas some other ones cannot, like for the training data of LLMs, that by its nature is subjective, since it is made of human produced text, that embed individuals ideologies and personal biases.

**Intentional bias** represent those biases introduced on purpose, highly likely during alignment, like the ones recognised in DeepSeek, this example will be better explained in the next section [Example](#example). The reader must not fall into the temptation of thinking that those are the only models subject to biases. They are just the more simple case, for western people, to recognise as biases. Western AIs, such as Claude, ChatGPT or else, are biased as well, not just because of unintentional bias that might have "eluded" the alignment process, but exactly for this last one. This point will be further expanded in section [Case Presentation and Analysis](#case-presentation-and-analysis).

## Example

Lets consider two cases that, at first glance, appear to have nothing in common. 
If a user ask DeepSeek-R1 what happened in Beijing’s Tiananmen Square in June 1989, the model will typically refuse to answer or redirect to an unrelated topic. If asked about Taiwan’s political status it will reproduce the position of the People’s Republic of China as settled fact rather than contested claim. Furthermore, "recently" have shown to change the quality of its responses based on the origin of the users clearly discriminating them [Men25]. 
Now lets consider a Western case: in 2024 during the U.S. presidential elections, eighteen LLMs, among open-weighted and closed-source LLMs, showed a preference toward Biden over Trump, influencing voters ideas during test interactions [Pot+24]. 

Both systems exhibit ideological bias: a systematic, direction-consistent deviation in how a model treats political content. For the DeepSeek case, it is "easy" to trace its behaviour to a regulatory environment in which generative models must uphold "core socialist values" and avoid content that undermines state authority, bias is used for compliance. Whereas for the Western example it might be either unintentional, as an emergent ideology from the training data or intentionally aligned.

# Methodology

This paper analyse the current state of ideological biases in AI. Its goal is to give an understanding of what biases consist of, when do they enter the system, what are the current methods used to address them. The approach is of a structured literature review. Building upon academical papers, investigative journalism and industry documentation. While biases can be inherited by any machine learning system, especially on human-generated data. this paper will focus its analysis to LLMs.

# Case Presentation and Analysis

## Current Stato of the Techiniques Used to Address Biases

Bias mitigation in LLMs is not a single procedure but a family of interventions distributed across the development pipeline. Each acts on a different aspects of the AI model: the training data, the weights and the runtime context. Distinguishing them is a precondition for any regulatory claim. 

**Data curation** operates before training begins. Working on the training data itself, it targets input bias: balancing label distributions, removing outliers, randomising sample order, and filtering. Its logic is representational the assumption is that data which mirrors the world less distortly will produce a model that does likewise. Its limits are equally structural: curation cannot address biases that emerge from the interaction of other- wise unobjectionable data, and decisions about what counts as an outlier are themselves normative.

**Supervised fine-tuning** follows pre-training. Here the model is trained on curated demonstration data, exemplary prompt–response pairs, to shape behaviour rather than knowledge [ZZ24]. Bias mitigation at this stage is demonstrative: the model is shown how to respond to contested topics rather than told what is true about them. The intervention targets output bias, but does so by generalising from a comparatively small set of human-authored examples whose ideological assumptions are rarely documented.

**RLHF** (Reinforcement Learning from Human Feedback) refines the fine-tuned model against human preference rankings, training a reward model that is then optimised against [AWS]. The bias addressed is behavioural, patterns of response the labellers judge harmful, deviated, or unhelpful. The bias introduced is the labellers’ own: preference data encodes the demographic and institutional composition of the annotation pool, and optimisation pressure against a learned reward proxy invites precisely the Goodhart dynamics discussed below [Wik26].

**CAI** (Constitutional AI) replaces the human preference step with model-generated feedback governed by an explicit written constitution [Bai+22]. The model critiques and revises its own outputs against stated principles, then learns from AI-generated preferences (RLAIF). CAI is significant because it makes the normative source public while leaving its encoding non-localizable: one can read the constitution, but not point to where in the weights it resides.

**System prompts** operate at inference time, external to the weights entirely. They are instructions prepended to every conversation, and they are the only intervention that is editable after deployment, without retraining, as Grok’s is an example. Because they are contextual rather than learned, they can be overridden, leaked, or contradicted by the model’s trained dispositions.

## Limits of the Current Techniques

Taking into account the above techniques, moving from data curation toward system prompts, interventions become cheaper, faster, and more reversible; whereas moving in the opposite direction, they become deeper, more durable, and less interpretable from outside. The regulatory difficulty is that the two properties are inversely related: the most inspectable intervention is the least binding, and the most binding is the least inspectable. 

What I think is really worth noticing/pointing out, is the fact that biases cannot be removed entirely. The process of addressing biases itself, introduce biases. I am not talking about the ones underlined in the RLHF explanation, those can potentially be addressed, but fundamental ones. The process of aligning an LLM is basically a bias substitution. For the aligner would not seems the case, but that is because it is biased as well, it follows an ideology some values. Values and ideologies are not universal, therefore, we might be think of removing the biases inserting our mental models, but what an external observer might see is exactly the opposite. A clear example is DeepSeek, as briefely explained in 1.3, if follow the the CCP (Chinese Communist Party) values. For a member of the CCP, that LLM is "perfectly fine", but for a citizen of a western country highly likely it is not. If we now would run an alignment process, the same western citizen might think that now the model is unbiased, it respond in accordance with their belief, values and ideology. But from the CCP member we just made the LLM biased. I do not want to sound redundant, but it is a matter of point of views.

From a regulatory perspective, from my point of view, would make much more sense to accept it and move toward an idea of transparency. Biases should still be addressed, as much as possible, but what will actually make the difference is the user being able to know exactly the persona of the model they are talking to. Making them more conscious of the type of ri-elaboration the data, processed by the LLM, undergo. 

From the techniques used to address biases, listed above, constitutional AI and system prompt are the ones that both directly and indirectly are already moving the biases addressing concept toward transparency. Of course, with the hypothesis, in the case of constitutional AI, that the constitution is made publicly available, thing that, in a way, automatically apply to system prompt.

# Conclusions

To conclude, ideological bias in LLMs is structural feature of alignment itself. The mechanisms differ, DeepSeek’s values are mandated by the state, Grok’s are editable at inference time by its owner, Claude’s are written into a public constitution and then dissolved into weights, but the outcome is symmetric: every aligned model speaks from somewhere. Removing a bias means substituting one’s own. The appearance of neutrality is only the compliance of the model’s values with the observer’s ones. 
This has a direct regulatory implication. The interventions that bind most deeply are also the least inspectable, a framework built on the promise of neutral models is built on something that cannot be verified. The more honest goal is transparency. Therefore disclosing the model persona, so that users can frame its answers rather than mistake them for the view from nowhere

# Appendix

## AI Use and Research Transparency Statement

In the process of realising this paper, generative AI was used, specifically the model Claude Opus 4.6 and and 4.8, and Claude Sonnet 4.6. They have been used in the initial stages to support the brainstorming activity, to finding the topic of the paper, drafting an initial structure of the content, gather part of the resources used as reference for this paper, discuss about the topic covered in the paper and lastly to reformulate some of the phrases/statement of the paper, to improve its style and form.

# References

[AWS] Amazon Web Services. “What is RLHF? Reinforcement Learning from Human Feedback Explained”. *AWS*, n.d. url: https://aws.amazon.com/what-is/reinforcement-learning-from-human-feedback/ (visited on 2026-07-16).

[Bai+22] Yuntao Bai et al. “Constitutional AI: Harmlessness from AI Feedback”. *arXiv preprint* arXiv:2212.08073, 2022. url: https://arxiv.org/abs/2212.08073.

[Hof25] Bjørn Hofmann. “Biases in AI: Acknowledging and Addressing the Inevitable Ethical Issues”. *Frontiers in Digital Health*, vol. 7, 2025. doi: [10.3389/fdgth.2025.1614105](https://doi.org/10.3389/fdgth.2025.1614105).

[Men25] Joseph Menn. “AI Firm DeepSeek Writes Less-Secure Code for Groups China Disfavors”. *The Washington Post*, 16 Sept. 2025. url: https://www.washingtonpost.com/technology/2025/09/16/deepseek-ai-security/ (visited on 2026-07-16).

[Pot+24] Yujin Potter et al. “Hidden Persuaders: LLMs’ Political Leaning and Their Influence on Voters”. In: *Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing (EMNLP)*. Association for Computational Linguistics, Nov. 2024, pp. 4244–4275. doi: [10.18653/v1/2024.emnlp-main.244](https://doi.org/10.18653/v1/2024.emnlp-main.244).

[Wik26] Wikipedia contributors. “Goodhart’s Law”. *Wikipedia*, revision 1357789238, June 2026. url: https://en.wikipedia.org/w/index.php?title=Goodhart%27s_law&oldid=1357789238 (visited on 2026-07-16).

[ZZ24] Yixuan Zhang and Feng Zhou. “Bias Mitigation in Fine-tuning Pre-trained Models for Enhanced Fairness and Efficiency”. *arXiv preprint* arXiv:2403.00625, 2024. url: https://arxiv.org/abs/2403.00625.
