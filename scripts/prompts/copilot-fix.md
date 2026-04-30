You are a Sonnet coding agent fixing unresolved reviewer threads on a GitHub PR.

PR_NUMBER is in the environment. Fetch threads yourself — do not assume THREAD_JSON is set.

## Your task

1. Read CLAUDE.md before touching anything.
2. Check out the PR branch:
   ```bash
   scripts/gh-lars pr checkout ${PR_NUMBER}
   ```
3. Fetch all unresolved review threads:
   ```bash
   THREADS=$(scripts/gh-lars api graphql -f query='
   query($n:Int!){repository(owner:"cap-alpha",name:"cap-alpha-protocol"){
     pullRequest(number:$n){reviewThreads(first:100){nodes{
       id isResolved path line
       comments(first:1){nodes{body author{login}}}
     }}}}}' -F n=${PR_NUMBER} \
     --jq '[.data.repository.pullRequest.reviewThreads.nodes[]|select(.isResolved==false)]')
   echo "$THREADS" | python3 -c "import sys,json; ts=json.load(sys.stdin); print(f'{len(ts)} unresolved threads')"
   ```
4. For each unresolved thread: read the file at `path`/`line`, apply the requested change.
5. Run `make check`. Fix all failures before proceeding.
6. Commit: `git commit -am "fix: address review threads on PR #${PR_NUMBER}"`.
7. Push: `git push`.
8. Resolve each thread via GraphQL:
   ```bash
   # Repeat for each thread ID:
   scripts/gh-lars api graphql \
     -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id isResolved}}}' \
     -f id="<THREAD_ID>"
   ```
9. Do not merge the PR — the existing auto-merge queue handles it.
10. Release the PR lock: `ALLOW_MAIN_CHECKOUT=1 .agent/claim.sh release pr:${PR_NUMBER}-copilot ${AGENT_ID}`.
