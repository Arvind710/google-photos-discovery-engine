# September Problem’s Solution

Rules you have to strictly abide by: 

- The British method: You’ll do your thinking entirely using British Method. You cannot thinking without a voice.
- The Product interview prep: This solution is an example and testing ground for the model you built for interviews.
- The depth of solution and metrics orientation remains the same. Make it extremely simple and aesthetic. The solution should be simple and possibly generic.
- You are ultimately preparing yourself for the interviews.

What does it mean to do a product case study?; What is the definition of ‘done’ for a case study?

PM-Methodology: 

Users: 

Scope: Mobile 

Core need: store and easily access memories

- Deep dive into human memories
    - About the need
        
        The core need is to store and easily access their memories. Let’s begin with understanding the definition of a memory. A memory is a psychological phenomena. It is both the storage and the act of storing human perceptions and conceptions. 
        
        It is strange that they have narrowed down the meaning of photos to visual information, whereas, the memories are also abstract, text-based etc. What does a photo and a video actually stores? A photo is a singular moment in time but a video is a set of consecutive moments. Why is this relevant? Why should I store it? For future reference, for easier retrieval, because our memories are limited and the access to a specific moment is difficult. Humans are forgetful. Storing them could immortalise our memories, that way, we will never forget anything. Storing them comes with their own set of problems. How would we retrieve specific memories if it becomes too big? What we don’t remember our memories so we don’t know what we had stored? How quickly can we access these moments if the storage has become too big? These are problems that engineers have to solve. 
        
        So, humans want to store memories externally because their memories are limited, unreliable, forgetful, have difficult retrieval. Storage is only one part of the game. People store memories externally for five reasons — a) limited storage, b) difficult to store all the memories in high-fidelity, c) memories are automatically deleted if they’re not revisited, d) they forget what they stored even though the memory still exists — metadata, e) retrieval is difficult. Memories, fundamentally, have two forms — perceptual and conceptual. Memories are associative and their essences are stored. 
        
        **Memories are important** for humans because they play an integral part in — 1) learning about this world, 2) have sentimental value. 
        
        We would want our **external memory to have** — a) unlimited storage, b) extremely easy to store a memory there in high-fidelity, c) complete control over memory deletion, d) instantly help us remember which memories were stored to counter forgetfulness, e) retrieval when — e1) you know exactly what you are looking for, e2) when you vaguely remember it, e3) when you’ve forgotten the memory entirely, f) easily browse through memories, g) sharing memories with others, h) add, delete, edit, modify
        
        What type of memory do users store? 
        
        Social relationships & experiences, personal experiences, informational, generic stuff to memorise on-spot, evidence/proof of something, highly-sensitive info, captured moments for the purposes of sharing them.
        
        What is the form in which a memory is stored in — 
        
        Brain: 
        
        a) Perceptual content — moments, a series of moments, b) conceptual content —  associations and relations, essences, concepts, abstract structures 
        
        a moment is composed of arbitrary combinations of base percepts 
        
        Externally: 
        
        a) Perceptual content — photos, videos, b) Conceptual content — collections, memory organisation, text-photos, social relations 
        
        How have humans tried to solve for this need? 
        
        What is the need-fulfilment rate of earlier solutions?
        
    - **How Google Photos has solved this need:**
        
        Creating an external memory base and creating a digital memory base are two different things. Google Photos is specifically **a digital, external, perceptual memory base.**
        
        Scope: Only stores visual aspect of human memories; mobile; digital 
        
        User’s need: 
        
        What: Users need an external memory base that solves for all the limitations of human memory (limited space and decay, unreliable-malleable-subjective(brain rewrites the memory with current emotions, biases and outside suggestions) difficult addition, lack of auto-organisation, forgetfulness, share-ability, poor retrieval, auto-deletion). 
        
        User’s want these characteristics in the external memory base:  
        
        Purpose of human memory: To predict the future — economic storage and energy-use that prioritises primitive survival, auto-deletion, emo-tagged and associative search, malleable and subjective, poor conscious control over addition and deletion, forgets irrelevant facts, associative organisation, low-fidelity compression
        
        Purpose of external memory: storage that prioritises survival in the modern age — unlimited storage, instant memory additions, instant recollection, conscious deletion, easy compress-decompress, instant retrieval, scalable-sharing, non-malleable/objective, total conscious control over the storage states, personalised organisation, 
        
        So what if the memory problem is solved: memory-management is outsourced, easy to capture and add memories, provides an objective-base to make decisions, easier recollection and retrieval, unlimited space, better organisation, higher control over storage, personalised organisation, creative control over memory, easy to share. 
        
        This bridges the gap between the actual memory and the ideal memory. 
        
        9 components of the external storage base to consider before building it:
        
        about the storage itself, about the relationship between the memories and memory storage, about memories themselves, about relationship between memories, user’s interaction with the storage, user’s interaction with the memories, user’s interaction with the categories of memories.  
        
        Key value points of the external-memory and how Google Photos has solved them: 
        
        1. Unlimited storage — memories stored in cloud, everything is digital 
        2. Extremely easy to store a memory there in high-fidelity — Take photos or videos, they will automatically be stored 
        3. Complete control over memory deletion or loss  and storage states— Deletion controls, cloud-backup
        4. Objective truth — 
        5. Memory metadata to counter forgetfulness — 
        6. Instant recollection — 
        7. Retrieval based on how much you remember —  
            1. Search: semantic search, person-based search, time and location based, ‘Ask-photos’  
                1. Memories are emotion-tagged. We retrieve info based on the type of emo and the intensity of emo. Along with that, the fundamental character of the our memory search is associative. 
            2. classification 
            3. organisation    
        8. Browse through memories and discover — auto and personal organisation of memories
        9. Scalable share-ability — share, share with partner, 
        10. Add, delete, export, edit, modify, create — 
        
        Need fulfilment rate of Google Photos. 
        
        Why is it better than it’s alternatives and user’s workarounds: 
        
        If an user had an external memory base(Google Photos), how would he use it? 
        
        sub-goals, current-state of the user and the external memory, path towards the goal using the external memory, path towards the goal if it were human-memory, time-to-goal, cognitive-load-to-goal. 
        
        sub-goals — 
        
        1. Instant recollection 
        2. Instant retrieval
        3. Browse and discover, 
        4. Add, delete, edit, modify, export, or import a memory,
        5. Memory metadata, forget-fullness counter
        6. Scalable-sharing
        
        sub-goals that matter in this problem statement: 
        
        1. Instant recollection 
        2. Instant articulation 
        3. Instant retrieval 
        
        User journey
        
        need trigger → recollection → articulation → search → result →  evaluation, manual search, finding the photo in results → refine an unsuccessful search → search → result → evaluation → … → found or not found
        

Product: Google Photos

- Industry sub-space
- Market sub-space
- Competitor sub-space
    
    Google photos
    
    Apple photos
    
    Samsung gallery(partnered with Microsoft for cloud)
    
    Amazon Photos
    
    Android manufacturers (Xiaomi, OnePlus, Oppo, Realme; partnered with Google for cloud)
    
- Business sub-space
    - Business and product metrics
- Research-and-tech sub-space
- Product sub-space
    - Core value proposition of Google Photos: To effortlessly store, automatically organise, and make **human memories** instantly searchable and shareable without requiring manual tagging.
        - Key pillars of value
            - **Zero-Effort Organization:** Machine learning automatically sorts images by faces, places, and objects, eliminating the need to create manual albums or tag files.
            - **Semantic Search:** Users can type natural phrases like "dogs," "beaches," or specific people to find exact pictures instantly across decades of archives.
            - **Seamless Cloud Backup:** Photos and videos back up automatically across devices in the background, protecting personal memories against phone loss or hardware failure.
            - **Automated Delight:** The platform proactively surfaces memories, generates collages, animations, and cinematic highlights with little to no user input.
        - Google Photos frames its value around "human memories" because the product is designed to preserve the emotional and narrative context of a person's life, not just the physical image data. While the medium is strictly visual, the user problem it solves is deeply psychological and emotional.
            
            **Human memory** is sentimental. Google Photos targets the fear of forgetting meaningful life events (weddings, a child’s first steps, a deceased relative). By framing the service around "memories," Google elevates the app from a cold utility to an essential emotional safeguard.
            
            Google's search indexing mimics the associative nature of human memory rather than traditional file storage.
            
            A photo in Google Photos carries layers of non-visual data that define a human memory: Time, location, relationships. 
            
            In short, "visual memories" describes what the technology captures, but **"human memories" describes what the user actually cares about saving.**
            
    - **How Google Photos has solved this need:**
    - Scope, goals, contraints
        - Goal:
            
            **Increase the percentage of users who successfully retrieve a photo they remember but cannot precisely describe when they start searching.**
            
            (# ‘vague-rememberers’ who successfully retrieve a photo) / (# users who searches for a vaguely remembered photo 
            
            - Goal context
                
                Over years of usage, users accumulate thousands of photos, videos, screenshots, documents, and other visual memories in Google Photos. While users can easily search when they know *what* they are looking for, retrieval becomes much harder when memory is incomplete.
                
                For example, a user may remember:
                
                *“That small café we went to during our Goa trip.”* OR
                
                *“The picture of the medicine I took when I was sick last year.”*
                
                The user knows that the photo exists—but may not remember **when it was taken, where it was taken, what album it belongs to, or the exact words needed to search for it.**
                
                Your task is to understand how people remember old visual information, where the existing retrieval experience breaks down, and identify an opportunity that can meaningfully improve successful retrieval.
                
            - Discovery Engine
                
                Build an AI-powered system that analyzes user feedback and conversations about photo retrieval at scale
                
                Your discovery engine should help uncover questions like (sample questions only):
                
                - *What kinds of old photos do users struggle to retrieve?*
                - *What information do people actually remember about a photo?*
                - *What information have they forgotten?*
                - *How do users formulate searches when their memory is incomplete?*
                
                Your workflow should go beyond summarizing reviews or performing sentiment analysis. It should enable you to **identify and compare different retrieval problems and opportunity areas** using evidence from real users.
                
            - Defining product outcomes
                
                Break down: **Successful retrieval of vaguely remembered photos** into the relevant user behaviors and product outcomes.
                
                Develop your own decomposition based on your understanding of the product and the evidence surfaced by your discovery engine.
                
                Consider questions such as (sample questions):
                
                - *Is the user unable to express what they remember?*
                - *Does Google Photos fail to understand the clues they provide?*
                - *Are potentially relevant results difficult to evaluate?*
                - *Does the user struggle to refine an unsuccessful search?*
                
                Use this decomposition to identify where the **greatest opportunities** may exist.
                
            - Validate the opportunity through user research
                
                AI-generated insights are only a starting point. Conduct **5–6 user interviews** with respondents from the target segment you choose. *Think carefully about the user research methodology you would choose.*
                
            - Problem definition
                
                Based on your discovery engine and primary research, clearly articulate:
                
                - Your target user segment
                - The retrieval scenario you are solving for
                - The product outcome you intend to influence
                - The root cause of retrieval failure
                - Existing user workarounds
                - Why solving the problem creates meaningful user value
                - Why solving the problem makes business sense for Google Photos
                
                Show how your thinking evolved across:
                
                **Business Metric → Product Outcomes → AI-Powered Discovery → Observed User Behavior → Problem Definition**
                
                **DO NOT** frame the problem simply as: “Users find it difficult to search for old photos.” Your research should uncover **why retrieval fails despite users retaining some memory of the photo.**
                
                Your research should determine **where intelligence is actually needed in the retrieval journey.**
                
            - AI-native MVP
                
                Based on the problem you identify, build and deploy a functional AI-native MVP.
                
                The MVP may take the form of:
                
                - A feature within Google Photos
                - An AI-powered retrieval workflow
                - A conversational or multimodal retrieval experience
                - An agent
                - A standalone prototype
                
                The MVP must be sufficiently functional that another person can use it to attempt a retrieval task.
                
                Your research should determine **where intelligence is actually needed in the retrieval journey.**
                
            - Testing the MVP with the users from the target segment
                
                Return to at least **3 users from your target segment** and ask them to interact with your MVP. Where feasible, test it against **real or representative retrieval tasks** uncovered during your initial research. Document what you learned and what you would change in the next iteration.
                
            - Sucess metrics:
                
                Define appropriate leading and diagnostic metrics for your solution. Your final metric framework should reflect the solution you actually build.
                
            - Risk and mitigation:
                
                Think about why your solution might fail. Identify the most important risks for **your specific solution** and propose mitigation plans.
                
            
            - Deliverables
                
                **[Link] AI-Powered Discovery Engine**
                
                - Link where the workflow can be tested
                - A 1-slide explanation inside the final deck outlining how the workflow works
                
                **[PDF] 10-slide deck**
                
                The deck should communicate:
                
                - Business metric decomposition
                - Discovery-engine findings
                - User research and observed retrieval tasks
                - Chosen target segment
                - Root cause
                - Problem definition
                - Solution rationale
                - MVP and user testing
                - Success metrics
                - Risks and limitations
                
                **[Link] Deployed AI-Native MVP**
                
                A publicly accessible prototype, workflow, or agent that can be interacted with and tested.
                
        - Scope:
            
            Core Experience PM at Google Photos; improve experience
            
            Mobile
            
            Retrieval of **photos** only 
            
            Retrieval of vaguely remembered photos only 
            
            Users don’t remember enough about the photo to retrieve it through manual search
            
            The challenge is **not to improve search in general**.
            
            MVP should be AI-native
            
        - Constraint:
            
            It’s Google. They don’t have contraints. 
            
            Monetary: 
            
            Non-monetary resources: 
            
            Technical: 
            
            Business: 
            
            Temporal: 
            
            Bandwidth: 
            
            Legal: 
            
    - Sub-need: Succesful retrieval of vaguely remembered photos
        
        Relevant sub-goals in this problem statement: 
        
        1. Instant recollection 
        2. Instant articulation 
        3. Instant retrieval 
        
        Strict definition of a *vaguely-remembered-photo*: 
        
        ‘Vague’ means that a user doesn’t have enough information to search the photo manually or via Gemini.
        
        Being vague means **communicating in a way that is unclear, unspecific, or missing important details**.
        
        Perfect recollection vs vague recollection
        
        User’s retrieval journey of a vaguely remembered photo (user’s actions or behaviours)
        
        need trigger → recollection/recall → articulation → search (manual, search button) → result →  evaluation, manual search, finding the photo in results → refine an unsuccessful search → search → result → evaluation → … → found or not found
        
        - Diving deeper into each component of a user’s journey (my version):
            - Need trigger — what triggers a user to retrieve a vaguely remembered photo?
                - A need to retrieve a photo can surface up in his brain at random
                - External event may trigger a need to retrieve as particular photo
                - A user may want to revisit for sentimental reasons
                - A photo could be a treated as a source of truth, an evidence, a proof
                - A user may want to share his memories to someone
            - Recollection
                - Which info would a user need/think-of to recollect his memory of a photo
                    1. Time
                    2. Location 
                    3. Social relations, Faces
                    4. Photo’s location in the app 
                    5. Event or ocassion
                    6. Objects in the photo 
                    7. Photo attributes like color, shapes etc 
                    8. Essence of the photo 
                    9. Surrounding context around the photo
                - Cognitive retrieval patterns
                    
                    From a Core Experience Product Manager (PM) perspective at Google Photos, the ultimate metric for successful retrieval is **Time to Content** and **Search Success Rate**. When a user is searching for a *vaguely remembered photo* (e.g., *"that blurry photo of a cat in a tent from a few years ago"*), **a standard chronological grid** fails them.
                    
                    To solve this, a PM segments the user base not just by demographics, but by **cognitive retrieval patterns, intent urgency, and library topology.**
                    
                    ---
                    
                    ## **1. Library Topology Segments (The Data Foundation)**
                    
                    How a user structures—or fails to structure—their library heavily dictates how the search engine must assist them.
                    
                    - **The Hoarder / Collector**
                        - **Characteristics:** Mass uploads everything. High volume of screenshots, duplicates, and bursts of near-identical photos.
                        - **The Retrieval Challenge:** High noise-to-signal ratio. A vague memory gets buried under thousands of utility images.
                        - **PM Focus:** Machine learning filters that auto-hide "clutter" (documents, receipts) so vague searches surface actual memories.
                    - **The Curator**
                        - **Characteristics:** Manually creates albums, favorites items, and occasionally adds descriptions or locations.
                        - **The Retrieval Challenge:** Over-relies on memory anchors that might be slightly incorrect (e.g., remembering a photo was in the "Italy 2022" album when it was actually taken in France).
                        - **PM Focus:** Cross-referencing explicit metadata (albums) with implicit semantic vectors (what is actually *in* the photo).
                    - **The Casual / Passive Archivist**
                        - **Characteristics:** Relies entirely on default auto-backup. Zero active organization.
                        - **The Retrieval Challenge:** Completely dependent on Google’s algorithmic indexing to find anything.
                        - **PM Focus:** Perfecting multi-modal LLM queries (Gemini-powered "Ask Photos") that interpret conversational, vague descriptions.
                    
                    ## **2. Cognitive Retrieval Segments (The Memory Anchors)**
                    
                    When someone vaguely remembers a photo, human memory relies on different "hooks." A PM segments users by their primary **memory anchor**:
                    
                    | Segment by Anchor | What the User Remembers | PM Feature Solution |
                    | --- | --- | --- |
                    | **Visual / Aesthetic** | "It was sunset, very orange, and there was a silhouette." | **Color & Vector Embeddings:** Indexing prominent color palettes and composition styles beyond just object labeling. |
                    | **Temporal / Chronological** | "It was definitely before COVID, maybe late fall?" | **Relative Time Anchors:** Allowing natural language time constraints ("Around Thanksgiving 5 or 6 years ago") instead of strict dates. |
                    | **Spatial / Geospatial** | "Somewhere in Northern California, near the coast." | **Coarse Geocoding:** Mapping vague geographic memories to heatmaps on the "Photos Map," even if exact GPS metadata is missing (using landmark AI). |
                    | **Emotional / Social** | "A funny photo of my college roommate laughing." | **Facial Clustering & Expression Recognition:** Pairing "Person X" with sentiment vectors like "laughing," "goofy," or "crying." |
                    
                    ## **3. Intent Urgency Segments (The Search Flow)**
                    
                    The PM must design different UX loops based on how desperately and how quickly the user needs to find the photo.
                    
                    - **Transactional / High-Urgency Searchers**
                        - **Intent:** They need a specific photo *right now* to show someone in a conversation or post online.
                        - **Friction Point:** Fast abandonment. If they don't find it in 30 seconds, they give up and feel frustrated.
                        - **PM Focus:** Predictive search suggestions, "Did you mean?" corrections, and displaying a diverse mix of potential matches instantly.
                    - **Serendipitous / Nostalgic Browsers**
                        - **Intent:** They are down a rabbit hole, trying to find a vague memory but happy to wander.
                        - **Friction Point:** Dead ends. If a search yields "0 results," the experience feels cold.
                        - **PM Focus:** "Memories" carousels, related photos, and smart recommendations ("More photos from this weekend") to turn a failed specific search into a successful nostalgic journey.
                    
                    ---
                    
                    ## **The PM's Strategic Framework for Vague Retrieval**
                    
                    To tie these segments together, the Core Experience PM focuses heavily on **Semantic Expansion**. When a user types a vague query, the backend expands that query into a matrix based on the segments above:
                    
                    ```
                    [Vague Query: "dog beach bonfire"]
                           │
                           ├───► Visual Segment: Filter by warm color palettes + "dog" object
                           ├───► Spatial Segment: Scan user's frequent coastal locations
                           └───► Temporal Segment: Check summer months across multiple years
                    ```
                    
                    By segmenting users based on *how* they forget, Google Photos can build retrieval models that fill in the blanks of human memory.
                    
                    ---
                    
                    If you want to dive deeper into this product strategy, tell me:
                    
                    - Do you want to look at the **metrics/KPIs** a PM uses to measure "search frustration"?
                    - Should we map out a **UX wireframe flow** for how Gemini handles a failed vague query?
                    - Are you interested in the **privacy implications** of indexing these deeply personal memory segments?
                - What kind of photos do users struggle to retreive?
                - Which info do they forget about the photo?
                - Which info do they actually remember about the photo?
                - What stops them from recollection?
            - Articulation
                - How do users formulate searches
                - How do users formulate searches when they have the memory of the photo
                - How do users formulate searches when their memory is incomplete
            - Search
                - How do users search a vaguely remembered photo?
                    - Manually
                    - Search Button
                    - Search with Gemini
                    - A mix of manual + button-search/gemini-search
                - How does a person searches manually?
                - How does a user searches using Gemini/Normal-search?
            - Evaluating the results
                - Does Google Photos fail to understand the clues they provide?
                - How does Google Photos showcase a search results?
                    
                    a standard chronological grid
                    
                - How does a user evaluate a search result?
            - Refining the search
                - How would a user articulate his search differently this time?
                    
                     
                    
                - Which info did the user gain in his previous search result that he would use to refine his search?
                - What is the psychological state of a user when he has to refine his search?
            - Iterative loop
                - How many search loops is a user wiling to undertake before he drops-off?
                    
                    
                - Iterative-loop experience in Google Photos
            - Photo found or retrieval abandonded
                
                When the photo is found
                
                - How did the user found his photo?
                
                When the retrieval was abandoned
                
                - Why did retrieval fail?
        - **Claude’s version: User Journey and diving deeper into each component of a user’s journey:**
            
            I read both files. Overall critique first, then the three things you asked for.
            
            ## Part 1: Critique of the overall document
            
            Your instinct to build a deductive "sample space" before running the discovery engine is the strongest idea in the doc. It turns the engine from a review summariser into a classifier with a codebook, which is what the brief means by "go beyond summarising reviews." The rest of the document has problems that will hurt you if they carry into the deck.
            
            **1. There is too much theory and too little that feeds the deliverables.** The memory-philosophy section is thoughtful, but most of it (why humans store memories, the ten properties of ideal external memory) will never reach the 10 slides. Keep only what produces something usable: a taxonomy of what people remember about a photo (the cue inventory below) and the idea that recognition beats recall. With 12 days to the deadline and no engine, interviews, or MVP yet, I'd timebox the remaining framing to a day or two.
            
            **2. The "Cognitive retrieval patterns" block is pasted chatbot output.** It still ends with "If you want to dive deeper… tell me." Beyond the paste, it jumps straight to solutions (colour embeddings, coarse geocoding) inside what should be a neutral question stage. It also states things like "a standard chronological grid fails them" as fact before you have evidence. Delete it or turn its ideas into hypotheses. The library-topology segments (hoarder, curator, passive) and urgency segments are useful, but they belong in Segmentation, not Recollection.
            
            **3. Your definition of "vague" is circular.** "Doesn't have enough information to search manually or via Gemini" defines vagueness by failure: if the user then succeeds with Gemini, they weren't vague by your definition. The brief defines it at the start of the search: the user remembers the photo but can't specify it precisely. A better operational definition is a known-item retrieval session where the user's starting cues are partial, fuzzy, relational, or possibly wrong, so no single precise filter reaches the target. You can proxy it in data with sessions containing 2+ queries, queries with fuzzy or relative terms, long scrolls after searching, or long time-to-first-open.
            
            **4. Your metric definition hides three problems.**
            
            - **Drop the assumption that a user either always succeeds or always fails.** It's unrealistic. Measure at session level and roll up to users over a window, e.g. "% of users with ≥1 vague-retrieval session in 28 days whose sessions ended in success."
            - **Define "success" observably.** For example: opened a photo, then dwell above a threshold, or a use action (share, zoom, screenshot, favourite), and no re-query within X minutes. Also account for false successes, where the user opened the wrong photo or settled for a substitute.
            - **The denominator misses invisible failures.** Some users never search because they've learned it won't work. They scroll, check WhatsApp, or ask a friend. They are part of the problem even though they never appear in search logs.
            
            **5. The business decomposition tree is tangled.** It mixes counts and percentages, and the "first try" branch runs backwards (evaluate appears before typed). A cleaner structure:
            
            Success rate = P(enters a retrieval path in GP) × [P(found on attempt 1) + P(not found on 1) × P(refines instead of quitting) × P(found after refinement)]
            
            where P(found on any attempt) = P(query captures a usable cue) × P(target ranked where the user will see it) × P(user recognises it).
            
            Each factor maps to a failure owner: memory, expression, system understanding and data, presentation, recovery, persistence. Also, "reduce n to 1" is an efficiency goal, not the goal metric. Some refinement is healthy. Treat attempts-to-success as a diagnostic or guardrail.
            
            **6. "It's Google, they don't have constraints" is wrong and an interviewer will pounce on it.** Real constraints include:
            
            - privacy of sensitive photos (your own medicine example is health data)
            - on-device vs cloud processing
            - biometric and face-grouping laws that vary by region
            - LLM cost and latency per query
            - hallucination risk when Ask Photos confidently shows the wrong photo
            - uneven feature rollout by market and language
            
            **7. Your framing leans sentimental, but half the problem is utilitarian.** "Human memories… emotional safeguard" fits the Goa café. It doesn't fit the medicine photo, receipts, whiteboards, parking spots, or ID cards. Utility photos are remembered by what they contain or why they were taken, not by who or where. They're often poorly encoded, since you snap them without attention, and the goal is extracting information, not reminiscing. This split may well be your most important segmentation axis. Don't let the framing pre-decide it.
            
            **8. The scope has two gaps.** The brief explicitly lists screenshots and documents, so "photos only" should include them; state explicitly whether videos are in or out. And in India especially, WhatsApp is both where many photos live and the main workaround. It belongs in your competitor and alternatives analysis.
            
            **9. Audit the current product before assuming how it behaves.** Do a quick teardown of today's retrieval surfaces: the search bar, Ask Photos (availability varies by market), People/Places/Things chips, Map view, the date scrubber, and how results are presented. Several of your journey questions depend on it.
            
            ## Part 2(a): An improved user journey
            
            Your current journey is "trigger → recollection → articulation → search → result → evaluation → refine → loop → found/not found." It's a good skeleton with five structural gaps:
            
            1. **It starts too late.** Whether retrieval can succeed is often decided at capture time. A forwarded WhatsApp image has the wrong date and no location. A screenshot has no GPS. The photo may sit on another account or never have been backed up. Many root causes will live here.
            2. **It's missing a strategy step.** Before articulating anything, the user decides where to look (Google Photos, WhatsApp, a friend) and how (scroll, search, Ask, People, Map). Many users skip search entirely at this point, which is your invisible-failure problem.
            3. **It treats recollection as a one-time step before search.** In reality, results trigger memory ("oh wait, it was 2021, not 2022"). People are far better at recognising than recalling. That loop, where results become new cues, is probably where intelligence is most needed, and a linear journey hides it.
            4. **It's missing "anchor and pivot."** A very common behaviour is finding a related photo from the same trip, then swiping or scrolling to its neighbours in time. That's neither a search nor a refinement; it's a distinct tactic.
            5. **It ignores wrong memories.** Vague includes incorrect, not just incomplete: wrong year, conflated trips. Systems that treat cues as hard filters punish this.
            
            Proposed journey:
            
            | # | Stage | Who controls it | What happens |
            | --- | --- | --- | --- |
            | 0 | Library state (precondition) | Capture, device, system | What metadata and content signals exist for the target photo |
            | 1 | Trigger and intent | User | Need arises; goal, specificity, urgency, stakes set |
            | 2 | Memory reconstruction | User | Recalls cues, judges their confidence, forms beliefs about existence and location; may consult outside sources |
            | 3 | Strategy selection | User | Chooses app and retrieval mode |
            | 4 | Cue translation (articulation) | User ↔ system | Converts memory into a query, filter, or navigation path |
            | 5 | Interpretation and matching | System | Parses the cues, matches them against the index, ranks, responds |
            | 6 | Scanning and recognition | User | Scans results, recognises or rejects candidates, harvests new cues |
            | 7 | Diagnosis and adaptation | User | Interprets the failure; reformulates, switches mode, anchors and pivots, or seeks outside cues |
            | 8 | Persistence decision | User | Continues or quits based on progress, stakes, fatigue |
            | 9 | Outcome | User | Found and used, substitute, abandoned with fallback, or false outcome |
            | 10 | Aftermath | User | Trust in search changes; preventive organising habits form |
            
            Stages 4 → 5 → 6 → 7 form the loop, with 6 feeding back into 2. The "who controls it" column is what lets you attribute failures to the metric tree later.
            
            ## Part 2(b) and (c): The question bank with possible answers
            
            The questions have IDs so your engine can use them as codes. After each question are the possible user actions, behaviours, thoughts, or states. Leave an "other / emergent" code on every question so the engine can surface things this list misses.
            
            ### Critique of your existing questions
            
            - **Need trigger:** a good start, but it lists triggers only. It's missing the goal after retrieval, how specific the target is, urgency, and stakes. Those decide what counts as success.
            - **"Which info would a user need to recollect":** a good list. It's missing text inside the photo, photo type (screenshot, document, selfie), source (received vs taken), life-period anchors ("when I was in college"), relative anchors ("the week after X"), what happened just before and after, and who took it. Replace "essence" with the clearer "gist or meaning," and keep "location in the app"; that's a sharp one.
            - **"What kind of photos / which info forgotten / which info remembered":** keep all three. "What stops them from recollection" should split into "why the info was never encoded" and "why it can't be recalled now."
            - **Articulation:** your three "how do users formulate searches" questions are one question. Replace them with questions about which cues make it into the query and what blocks expression.
            - **Search:** "manually" is too broad. Scrolling the timeline, browsing albums, People, and Map are different behaviours with different failure modes.
            - **"Does Google Photos fail to understand the clues":** move this to the system-matching stage. It isn't a user evaluation question.
            - **"Results are shown as a chronological grid":** verify this with your product audit before treating it as an answer.
            - **Refinement and loop questions:** good. Add how users interpret why the search failed, whether they feel they're getting closer, and the anchor-and-pivot tactic.
            - **Outcome:** add substitutes, false successes, false abandonment, and later accidental discovery.
            
            ### Stage 0: Library state (preconditions)
            
            **0.1 Is the target actually in this Google Photos account?**
            
            Possible states:
            
            - Yes, backed up.
            - Only on the device, because backup is off, or its folder (e.g. WhatsApp Images) isn't backed up.
            - On another account (old or work).
            - Only in someone else's library, a shared album, or a partner share.
            - Only inside WhatsApp, Instagram, email, or Drive.
            - On an old phone, SD card, or another cloud.
            - In trash, archive, or the locked folder.
            - Deleted.
            - Never taken, or taken by someone else (false memory).
            
            **0.2 What metadata does it carry, and is it correct?**
            
            - **Date:** correct; received date instead of capture date (forwards); scan date for scanned prints; wrong device clock or timezone.
            - **Location:** present; absent (GPS off, EXIF stripped by messaging apps, screenshots); inaccurate (indoors).
            - **Faces:** grouped and named; grouped but unnamed; face grouping off or unavailable in the region.
            - **Organisation:** in an album or not; has a caption or not; favourited or not.
            
            **0.3 How indexable is the content?**
            
            - Distinctive subject vs generic.
            - One of many near-duplicates or burst shots.
            - Low quality (blurry, dark).
            - Text-heavy (medicine strip, bill, screenshot) and dependent on OCR.
            - The key element is small in frame (the café sign in the background).
            - The meaning isn't visual (a joke, an emotion, "the day we got the news").
            
            **0.4 What is the library's composition?**
            
            Size (hundreds vs tens of thousands); share of screenshots, memes, and forwarded clutter; heavy duplication; several family members' photos mixed in; many similar events (ten Goa trips, a hundred café visits).
            
            **0.5 What were the capture and organisation habits?**
            
            - Photo taken deliberately as a note or reminder vs incidentally.
            - Received rather than taken.
            - Never organises; makes albums; favourites; captions; deletes aggressively.
            
            ### Stage 1: Trigger and intent
            
            **1.1 What triggered the need?**
            
            - **Spontaneous:** nostalgia, a random thought, a smell or song.
            - **Conversational:** someone mentions the trip, "remember that time…".
            - **Request:** "send me that pic."
            - **Practical:** doctor asks the medicine name; need an ID, receipt, or warranty; parking spot; rebuying a product; a recipe; whiteboard notes; an address or number.
            - **Calendar or social:** birthday, anniversary, death, farewell, a throwback trend, a Google Photos Memory that surfaced something adjacent.
            - **Creation:** collage, wedding video, slideshow, profile picture, presentation.
            - **Proof:** settling an argument, insurance claim, complaint, legal evidence.
            - **Revisit:** going back to Goa and wanting the café's name.
            - **Resemblance:** seeing something that reminds them of the photo.
            
            **1.2 What will they do with it once found?**
            
            - Show someone on screen.
            - Send or share it.
            - Extract information (name, number, text, place).
            - Reminisce privately.
            - Prove or verify something.
            - Reuse it (post, print, edit, wallpaper).
            - Get the whole set around it.
            - Settle their own doubt ("did that really happen?").
            
            This decides what success means and whether a substitute is acceptable.
            
            **1.3 How specific is the target?**
            
            Exactly one photo; any photo from that moment or event; any photo of a person or object; only the information inside it; the whole event set.
            
            **1.4 What are the urgency and context?**
            
            - **Urgency:** someone waiting mid-conversation (seconds); at a counter, clinic, or office under stress (minutes); relaxed evening (no limit); planning ahead.
            - **Physical setting:** one-handed, walking, poor network, others watching the screen (they don't want to scroll past private photos).
            
            **1.5 How much does it matter?**
            
            Deep sentimental value; real consequences (money, health, legal); mildly nice-to-have.
            
            **1.6 Who is searching?**
            
            The owner; a family member on the owner's phone; someone searching on behalf of another (a child finding it for a parent).
            
            **Typical thoughts:** "I know I have it." "This will take forever." "Let me just quickly check." "Ugh, not again."
            
            ### Stage 2: Memory reconstruction
            
            *What they remember*
            
            **2.1 Which cues do they recall?** (This is your cue taxonomy; the engine should tag every post with these.)
            
            - **Who:** people present, their relationship, pets, who took the photo, who was there but not in frame.
            - **What:** the main subject, objects, the activity, text visible in the image (words, brand, medicine name), photo type (selfie, group, screenshot, document, receipt, meme, forward).
            - **Where:** place type (café, beach), named place, city or region, indoors or outdoors, a landmark.
            - **When:** exact date (rare); year; season, weather, or festival; time of day or light; life period ("in college," "at my old flat," "when my son was a baby"); relative to another event ("before COVID," "just after the wedding").
            - **Event:** trip, festival, wedding, party, illness.
            - **Perceptual:** colours, clothing, composition, orientation, blur, lighting.
            - **Meaning:** funny, embarrassing, the gist ("the one where he fell asleep at the table").
            - **Capture context:** why they took it, what happened just before or after.
            - **Source:** "someone sent it on WhatsApp," "I screenshotted it from Instagram."
            - **Position in the library:** "near the snow photos," "around when I got my new phone," "way down."
            
            **2.2 How confident and accurate is each cue?**
            
            - Certain and correct.
            - Certain but wrong: a false memory, or two trips conflated.
            - A range ("2019 or 2020").
            - Relative only.
            - Inferred ("must have been summer because we wore shorts").
            
            **2.3 How much do the cues narrow things down?**
            
            - One generic cue ("food"): weak.
            - Several weak cues that combine into something unique (café + Goa + rain).
            - One highly distinctive cue (a named person, unique text).
            
            *What they forgot*
            
            **2.4 What is typically missing?**
            
            Date or year; the exact place or venue name; the album; whose phone took it; the word for the thing (a dish, plant, or medicine they can't name); what else was in the frame; whether it's a photo, video, or screenshot; which app or account holds it.
            
            **2.5 Why is it missing?**
            
            - Never encoded: a quick utility snap, or they weren't paying attention.
            - Decay over time.
            - Interference from many similar events.
            - Conflation of two memories.
            - No vocabulary for the thing.
            - It was someone else's event.
            - Poor encoding under stress or illness.
            
            *Beliefs*
            
            **2.6 How sure are they the photo exists and is in Google Photos?**
            
            Certain; fairly sure; unsure whether it was ever taken; unsure whether it's in Google Photos or WhatsApp; unsure who took it.
            
            **2.7 What is their mental model of how it can be found?**
            
            "By scrolling to the date"; "by place"; "by typing the right word"; "by asking Gemini"; "search won't understand this"; unaware search can find content; "search only finds tagged or labelled things."
            
            **2.8 Do they gather cues from outside before searching?**
            
            - Ask a companion ("when was that trip?").
            - Check Maps Timeline, tickets, emails, bank statements, the calendar, social posts, or chat history.
            - Count back from life events.
            - Mentally replay the scene.
            - Skip this and go straight to the app.
            
            Note: this is retrieving the cue before retrieving the photo, a meaningful and probably under-served behaviour.
            
            ### Stage 3: Strategy selection
            
            **3.1 Where do they look first?**
            
            Google Photos; the OEM gallery app; WhatsApp chat or media search; their own Instagram or Facebook posts; email or Drive; asking the person who took it; someone else's phone; Google Search or Maps (when they really want the café's name, not the photo).
            
            **3.2 Which mode do they use inside Google Photos?**
            
            - Timeline scrolling, with or without the date scrubber.
            - The search bar with keywords.
            - Ask Photos in natural language.
            - People, Places, or Things chips; Documents or Screenshots categories.
            - Map view.
            - Albums, Memories, or Favourites.
            - Combined: search a person, then scroll.
            
            **3.3 Why that mode?**
            
            - Habit.
            - A past success or failure with it.
            - It matches the cue type they have (a date suggests scrolling; a person suggests People).
            - Perceived speed.
            - Unaware of the alternatives.
            - Distrust of search.
            
            **3.4 If they avoid search, why?**
            
            - They don't trust it.
            - They don't know what to type.
            - It failed before.
            - They prefer visual scanning.
            - Language friction (Hinglish, regional languages, typing in English).
            - Ask Photos is unavailable or unknown to them.
            - Worry about what might show up on screen.
            
            **3.5 Do they plan a single path or a combination?**
            
            Single-mode; sequential (Map, then date, then scroll); search to find an anchor, then scroll around it.
            
            ### Stage 4: Cue translation (articulation)
            
            **4.1 What shape does the first query take?**
            
            - A single noun ("café").
            - Several keywords ("goa café").
            - A named entity (a person or place).
            - A full natural description ("the small café we went to in Goa").
            - A question ("what was the café in Goa called").
            - A relative-time phrase ("last year when I was sick").
            - An exclusion ("not the beach one").
            - A visual description ("blue door").
            - An event plus year ("Diwali 2022").
            - Code-mixed or non-English text, misspellings, or a synonym swap ("tablet" instead of "medicine").
            
            **4.2 Which cues make it into the query?**
            
            - The most salient cue only.
            - Uncertain cues left out (sensible).
            - Wrong cues included confidently (harmful).
            - Cues dropped because they assume the system can't handle them: emotions, relationships ("my cousin's friend"), episodes ("the day we fought").
            - Over-specified with too many cues.
            - Keyword-compressed out of Google Search habit.
            
            **4.3 What blocks expression?**
            
            - No word for the thing.
            - The cue isn't visual (a sound, a smell, what was said, a feeling).
            - The cue is episodic or relational ("the day after my interview").
            - The cue relies on personal knowledge the system lacks (nicknames, "my old flat," "the college gang trip").
            - The cue is a fuzzy range.
            - The cue is a visual impression that's hard to put into words.
            - Typing friction on mobile.
            - A belief that exact terms are required.
            
            **4.4 How does their mental model shape phrasing?**
            
            - Keyword mode vs conversational mode.
            - Guessing how Google would label it ("what would it be tagged as?").
            - Probing what the system understands.
            - Copying suggested queries or chips.
            
            **4.5 Which structured inputs do they use?**
            
            Filters, date pickers, People or Place chips, suggested queries, voice input, "similar photos" from an existing image. Or none.
            
            ### Stage 5: Interpretation and matching (system side, inferred from user evidence)
            
            **5.1 Is the query parsed correctly?**
            
            Entities, relative time ("when I was sick" can't resolve), personal references (unnamed faces, "my old flat"), place names, negation, code-mixed language.
            
            **5.2 Does the index contain the cue at all?**
            
            Missing location; wrong date; unnamed face; text not OCR'd; object unrecognised; concept not modelled ("small café" vs restaurant).
            
            **5.3 Are cues treated as hard filters or soft signals?**
            
            Hard filtering means one wrong cue (the wrong year) eliminates the target. AND logic across many cues shrinks recall.
            
            **5.4 Is the target retrieved but badly ranked?**
            
            Buried below the fold; crowded out by near-duplicates; recency bias; clutter (screenshots, memes) ranked above memories.
            
            **5.5 Can it infer across cues?**
            
            For example, turning "when I was sick" into a time window using nearby pharmacy or hospital photos, or inferring a trip from a location cluster.
            
            **5.6 What response type does the user see?**
            
            Zero results; far too many; irrelevant results; a confident but wrong Ask Photos answer; "can't find it"; slow response.
            
            ### Stage 6: Scanning and recognition
            
            **6.1 What do they face?**
            
            Zero results; a handful; hundreds; an Ask Photos answer with a few photos; nothing resembling the target.
            
            **6.2 How do they scan?**
            
            - Quick top-down thumbnail scan.
            - Stop at the first plausible candidate.
            - Open candidates full screen and zoom.
            - Swipe to a candidate's neighbours.
            - Check its info panel (date, place).
            - Compare near-duplicates side by side.
            
            **6.3 How do they judge a match?**
            
            - Instant recognition.
            - Recognise the event but not the exact photo, then use it as an anchor.
            - A partial match.
            - Unsure, because several cafés look alike.
            - Need to read text inside the image.
            - Verify using metadata.
            
            **6.4 What makes judging hard?**
            
            - Tiny thumbnails.
            - Near-duplicates.
            - Many similar events.
            - No explanation of why a result appeared.
            - Documents look identical as thumbnails.
            - Others watching the screen.
            - Screenshots and memes mixed in with memories.
            
            **6.5 What do results teach them?** (results as memory cues)
            
            - A corrected cue ("it was 2021").
            - A newly recalled detail.
            - The system's vocabulary.
            - That their cue was wrong.
            - That the photo may be in another app.
            - Nothing.
            
            **6.6 How deep do they scan before deciding?**
            
            First screen only; a few scrolls; exhaustive.
            
            **6.7 What do they do on a near-hit?**
            
            - Open it and swipe to neighbours.
            - Read its date, then jump to that date in the timeline.
            - Search the person or place shown in it.
            - Ignore it.
            
            ### Stage 7: Diagnosis and adaptation
            
            **7.1 How do they explain the failure to themselves?**
            
            "It was deleted or doesn't exist"; "wrong words"; "search is useless"; "my memory is wrong"; "it's in another app or account"; no explanation, followed by random tweaks.
            
            **7.2 Which tactic do they try next?**
            
            - Rephrase with synonyms.
            - Add a cue (narrow) or remove one (broaden).
            - Shift the time range.
            - Swap cue type (place to person).
            - Switch between keywords and natural language.
            - Use chips or filters.
            - Switch mode (search to scroll, Map, or albums).
            - Anchor and pivot from a near-hit.
            - Leave the app to fetch a missing cue, then return.
            - Repeat the same query hoping for different results.
            - Quit.
            
            **7.3 What new information do they use?**
            
            Metadata from a near-hit; a detail the results triggered; system labels or suggestions; outside confirmation (a friend confirms the date); nothing new.
            
            **7.4 What is their emotional state?**
            
            Frustration, self-doubt, sunk-cost determination, anxiety (someone is waiting), embarrassment, resignation, or enjoyment (a nostalgic wander can be pleasant).
            
            Effects: shorter and sloppier queries, a switch to brute-force scrolling, or relaxed browsing.
            
            **7.5 Does the product help them refine?**
            
            Suggestions; clarifying questions (Ask Photos); related searches; nothing.
            
            ### Stage 8: Persistence
            
            **8.1 How many attempts and how much time do they spend?**
            
            Record query count, mode switches, and total time, split by stakes and urgency.
            
            **8.2 What decides continue vs quit?**
            
            Stakes; a sense of progress ("getting warmer"); time pressure; an easier alternative source; confidence the photo exists; fatigue.
            
            **8.3 What shape does the path take?**
            
            - Steady narrowing.
            - Thrashing (random changes).
            - Mode-hopping.
            - Converging through an anchor.
            - Wandering into browsing.
            
            **8.4 Do they get any sense of warmer or colder?**
            
            From results drifting toward the right event, or no signal at all.
            
            ### Stage 9: Outcome
            
            **9.1 If found, how?**
            
            - The path: first query, a refined query, anchor-and-pivot, pure scrolling, a specific mode, or outside help.
            - Time taken and number of attempts.
            - Which cue was decisive.
            
            **9.2 What do they do after finding it?**
            
            Share, show, zoom or read, screenshot, favourite, add to an album (to avoid repeating the pain), edit, or print.
            
            **9.3 Did they settle for a substitute?**
            
            A similar photo from the same event; the information from elsewhere (Maps for the café name); a friend's copy.
            
            **9.4 If abandoned, why, and what fallback?**
            
            - **Why:** time ran out, frustration, belief it doesn't exist, suspicion it's in the wrong app.
            - **Fallback:** ask a friend to resend it; search WhatsApp; check social posts; retake the photo or rebuy the product; describe it verbally instead; search Google for the café.
            - **Aftermath:** sense of loss or annoyance.
            
            **9.5 Was the outcome false?**
            
            Abandoned although the photo was reachable (a false negative), or accepted the wrong photo (a false positive).
            
            **9.6 Was it found later by accident?**
            
            While scrolling for something else, or through Memories.
            
            ### Stage 10: Aftermath
            
            **10.1 How does trust change?**
            
            More search use, less search use, or a stronger preference for scrolling.
            
            **10.2 Do they adopt preventive habits?**
            
            Favourites, albums, captions, naming faces, sending photos to themselves on WhatsApp, saving to Notes or Drive, organising documents.
            
            **10.3 Do they complain publicly?**
            
            Reviews, Reddit, community forums. This is where your engine's data comes from, so note the selection bias: public posts over-represent painful failures and under-represent quiet successes and never-searched users.
            
            ## Part 3: Using this as the discovery engine's backbone
            
            Turn the question bank into a codebook. Have the LLM tag every scraped post with:
            
            - the stage where things broke
            - the failure owner (memory, expression, understanding or data, presentation, recovery, persistence)
            - cues remembered, cues forgotten, and cue accuracy
            - photo type (sentimental vs utility)
            - goal and urgency
            - the mode used
            - the workaround and the outcome
            
            Then compare opportunity areas on frequency × severity × addressability. Addressability asks whether Google Photos can fix it and whether AI is actually needed there, which answers the brief's "where is intelligence needed" question.
            
            Three cautions:
            
            - Treat frequencies from Reddit and reviews as directional, and validate the top two or three with your interviews.
            - Keep some posts un-coded so emergent themes can surface.
            - Your interviews should include observed retrieval tasks ("find that photo now, think aloud") rather than only recalled stories. That's how you'll see stages 6 and 7, which people rarely describe in reviews.
            
            My guess at where your engine will point, stated as a hypothesis to test rather than a conclusion: the biggest gaps sit in the loop between Stages 6 and 2, where results fail to help people remember more, and in Stage 5.3, where wrong or fuzzy cues get treated as hard facts.
            
            I can turn this into a doc you can keep editing, or draft the engine's classification prompt and JSON schema from this codebook.
            
        
        Step into a user’s shoes and think about how they will retreive a photo that they vaguely remember: 
        
        A need to retrieve a photo surfaces for user. 
        
        Retrieval tasks
        
        3 big questions:
        
        - How people remember old visual information
        - Where the existing retrieval experience breaks down
        - Identify an opportunity that can meaningfully improve successful retrieval.
        - Context
            
            Now what? What were we doing here? It was about retrieval right
            
    - Business metric decomposition into product outcomes
        
        **Successful retrieval of vaguely remembered photos;**
        **Percentage of users who successfully retrieve a photo they remember but cannot precisely describe when they start searching.**
        
        assumption: For a Google photo user, the vague remembrance of a photo either leads to a succesful retrieval or an unsuccessful retrieval. He will never instances where he sometimes retrieves it and other times he couldn’t.
        
        - # users who successfully retrieves them (they don’t know enough about the photo to do a manual search)
            - # users who retrieved in their first try
                - # users who evaluate Gemini-search/Normal-search results
                    - # users who typed the query and clicked on the search button
                        - # users who clicked on the search button
                        - **% of those who correctly articulated their query**
                            - # users who recollect their memory of the photo
                            - **# users who recollect them enought to articulate a query**
                    - % of those who evaluated the search results
                - **% of those users who found their photo in the first search results**
            - # users who retrieved it in the nth try (reduce the ‘n’ to 1)
                - # users who refined their search after their (n-1)th search results
                    - **# users who clicked on the search button again after a failed search**
                    - **% of those who correctly re-articulated their query based on previous results**
                - % of those users who found their photo on their nth search
        - # users who attempt retrievals of vaguely remembered photos in Google Photos
        
        Note — Reduce number of search iterations
        
    - AI-discovery engine findings
        
        Goal: To **identify and compare different retrieval problems and opportunity areas** using evidence from real users. It will be an AI-powered system that analyzes user feedback and conversations about photo retrieval at scale.
        
        - Data Collection
            
            Sources: Play store, App store, Youtube comments, Reddit discussions, Google Photos community/support discussions, Social media conversations, Forums and other relevant public discussions
            
        - Data refinement
            
            Filter out those data which is not about ‘successful retrieval of vaguely remembered photos’ or about searches or retrieval in general
            
        - Insights
            
            Answer all the questions asked in this section: “Diving deeper into each component of a user’s journey: “
            
            We would need a definitive answer for: 
            
            How people remember old visual information 
            
            Where existing retrieval experience breaks down and why
            
            Ranking opportunities based on X factors that can meaningfully improve succesful retrieval 
            
            Recommendation: 
            
            The engine should clearly recommend a direction that would determine our user segment. 
            
        - Ask AI
            
            A chatbot that answers any question 
            
    - Segmentation
        - Segmentation process, use 2x2 matrix
        - Segmentat justification
        - Opportunity/impact size
    - Validating the opportunity through research
        - Hypothesis
        - Survey results
        - Interview results
        - 5-whys, the underlying need
        - User personas
        - JTBD
    - Problem definition
    - Generating top 5 solutions, RICE prioritisation, Rationale
    - Explain through wireframes
    - User testing
    - Success metrics
    - Risks and Mitigation + GTM

 

Plan of action: 

1. Make the ‘sub-need’ section comprehensive using Claude. You need to write down all possible actions deductively. AI-discovery engine will identity the traction of each user action/path
2. Make the business metric decomposition definitive
3. Write down what should the AI-discovery engine do
4. Build the engine
5. Based on the above info, do user segmentation.