# Pipeline Details

## Assumptions
- The LLM outputs a correct breakdown of the changes made given the prompt
- The recipe page has a "Featured Tweaks" section
- The OpenAI account associated with the key has a positive balance

## Problems and Solutions

#### 1. I don't have a working (or funded) OpenAI API key
This would have been used to test if the pipeline work. Instead I created a script that will generate the prompt, and I pasted this prompt on my browser to get its response. Then, I created another script to apply these modifications to the recipe.

#### 2. The featured tweaks are confused with the reviews
The code uses the reviews that it finds and tries to classify whether it is a tweak or not using regular expressions. It uses the first review that the webpage returns that it thinks is a tweak to be the **top** featured tweak. To overcome this, I changed the entire naming convention of the codebase to use "tweak" instead of "review" for variable names associated in enhancing the recipe.

#### 3. The output of the LLM to the prompt sometimes hallucinates
Sometimes the output of the LLM to the prompt creates instructions that are not there, or yet takes substrings of real instructions making it difficult to order the enhanced instructions. To avoid this, the prompt was improved and given better clarity on the instructions.

#### 4. The scraper does NOT work as intended
The original scraper does not get the featured tweak, or it does not know which of the reviews is the featured tweak for the recipe. The featured tweak for the recipe sometimes appears in the reviews section but sometimes it does not. The featured tweaks for the recipes do not come with the initial GET request for the recipe. It is obtained by the browser creating a separate POST request to obtain it. Mocking this request is difficult, and causes errors due to authentication issues, instead I revamped the scraping method. Instead of using requests, the scraper now runs in a headless chromium process and opens the webpage from a browser. Here the browser will be able to make the POST request legitimately and we can obtain the featured tweaks for the recipes.

## Future improvements
- While repeatedly using the manual pipeline of copying and pasting the prompts to ChatGPT I encountered that the outputs can be different. I believed the prompt can be further engineered to be more stable.
- The pipeline also uses separate sessions for each prompt, and this consumes a lot of tokens. We can utilize system_templates to create our prompts to reduce redundancy
