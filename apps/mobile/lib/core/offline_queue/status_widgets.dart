import 'package:flutter/material.dart';

/// A shared "queued — will send when back online" confirmation banner.
///
/// Both the request form (T026) and the low-stock report screen (T032) show
/// this exact widget for a queued offline submission rather than each
/// inventing its own icon/text/key combination for the same state (FR-012 —
/// a queued item is never presented as confirmed).
class SubmissionQueuedBanner extends StatelessWidget {
  const SubmissionQueuedBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('submissionQueuedBanner'),
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Icon(
          Icons.schedule_outlined,
          key: Key('submissionQueuedIcon'),
          color: Colors.orange,
          size: 64,
        ),
        const SizedBox(height: 16),
        Text(
          message,
          key: const Key('submissionQueuedMessage'),
          style: Theme.of(context).textTheme.titleLarge,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
