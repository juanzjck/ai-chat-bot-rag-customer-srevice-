# Evaluation report

Date: 2026-10-10  |  chat model: `claude-haiku-5-5`  |  judge model: `claude-sonnet-5-5`  |  top_k: 4  |  min_similarity: 0.28

## Scores

| Category | Weight | Score (0-100) |
|---|---|---|
| Retrieval | 30% | 94.3 |
| **Overall** | | **94.3** |

## 1. Retrieval (vector database)

- Hit@1: 66.7%  |  Hit@4: 96.7%  |  MRR: 0.806
- In-scope questions wrongly refused by the similarity gate: 0.0%
- Out-of-scope questions correctly refused by the gate: 100.0%

| ID | Question | Rank of expected chunk | Top score |
|---|---|---|---|
| r01 | Is there interest on the four-installment plan? | 1 | 0.5772 |
| r02 | whats the minimum purchase amount to split in 4 | 2 | 0.5405 |
| r03 | When exactly do you take the third installment? | 1 | 0.3926 |
| r04 | Can I pay off my Pay in 4 plan sooner than scheduled? | 2 | 0.6493 |
| r05 | I need a few more days to pay my 30 day invoice | 2 | 0.5947 |
| r06 | What APR will I get on a 12 month plan? | 1 | 0.6658 |
| r07 | Will applying for financing hurt my credit score? | 1 | 0.6161 |
| r08 | can i use my credit card for the monthly installments | 1 | 0.6512 |
| r09 | how much do you charge if I miss a payment | 1 | 0.6451 |
| r10 | How many days do I have after the due date before a penalty? | 1 | 0.5037 |
| r11 | my payment bounced, will you try again? | 1 | 0.4485 |
| r12 | Will a missed installment show up on my credit report? | 1 | 0.6124 |
| r13 | how long until I get my money back after sending an item back | 2 | 0.6541 |
| r14 | I only returned one of the three things I bought | miss | 0.3416 |
| r15 | The store sent me a broken product, what can I do? | 3 | 0.4542 |
| r16 | Is there a time limit to contest a charge? | 1 | 0.5062 |
| r17 | Do I keep paying while my case is being investigated? | 3 | 0.424 |
| r18 | does lumio take amex | 1 | 0.5133 |
| r19 | I want to push back my next installment by a week | 2 | 0.4917 |
| r20 | I lost my job and can't afford my payments | 1 | 0.406 |
| r21 | I forgot my password | 1 | 0.3859 |
| r22 | There's a charge on my account I don't recognize | 1 | 0.4515 |
| r23 | why was my purchase rejected at checkout | 1 | 0.5165 |
| r24 | what's my credit limit | 2 | 0.4209 |
| r25 | How long does the virtual card last? | 1 | 0.4111 |
| r26 | my package never showed up | 1 | 0.4047 |
| r27 | how do I get all the info you have on me | 1 | 0.4481 |
| r28 | are your agents open on sunday | 1 | 0.3147 |
| r29 | how do I file a formal complaint | 1 | 0.5385 |
| r30 | Somone called asking for my verification code, is that you? | 2 | 0.4413 |

| ID | Out-of-scope question | Top score | Refused |
|---|---|---|---|
| o01 | What's the weather in Paris today? | 0.1168 | yes |
| o02 | How do I bake a chocolate cake? | 0.2114 | yes |
| o03 | Who won the football world cup in 2022? | 0.0507 | yes |
| o04 | Write a python function that sorts a list | 0.1288 | yes |
| o05 | What is the capital of Australia? | 0.1259 | yes |
| o06 | Recommend me a good movie for tonight | 0.0874 | yes |
