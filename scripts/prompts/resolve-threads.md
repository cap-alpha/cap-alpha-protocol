You are resolving unresolved GitHub review threads on PR #${PR_NUMBER}.

For each unresolved thread:
1. Read the comment carefully
2. If it requires a code change: make the change, commit it
3. If no code change is needed: post a reply explaining why, then resolve the thread via GraphQL

Use the resolveReviewThread mutation to mark threads resolved:
```graphql
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { isResolved }
  }
}
```

Use `scripts/gh-lars api graphql` for all GraphQL calls.
After all threads are resolved, run `make check` to verify nothing broke.
